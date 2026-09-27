"""Classeurs d'archivage : l'étagère, un classeur, et le constat de l'archiviste page par page.

Un réglementaire pays ne voit que les classeurs de ses pays ; le siège voit tout et peut
télécharger chaque classeur en PDF, tel qu'il apparaît à l'écran.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.amm.models import MarketingAuthorization
from apps.amm.serializers import django_to_drf_validation_error
from apps.core.dates import today
from apps.core.tasks import enqueue
from apps.documents.views import open_stored_file

from . import actions
from .layout import binder_detail, get_binder, shelf
from .models import BinderExport
from .pdf import binder_pdf
from .serializers import (
    AddPageInputSerializer,
    AddPageResultSerializer,
    BinderDetailSerializer,
    BinderExportSerializer,
    BinderSummarySerializer,
    CheckInputSerializer,
    ExtraPageInputSerializer,
    ExtraPageSerializer,
    PageScanInputSerializer,
    PageScanResultSerializer,
    UncheckInputSerializer,
)


class BinderViewSet(viewsets.ViewSet):
    lookup_field = "key"
    lookup_value_regex = r"[A-Za-z]{2}(?:-[a-z-]+)?"

    @extend_schema(responses=BinderSummarySerializer(many=True))
    def list(self, request):
        return Response(BinderSummarySerializer(shelf(request.user), many=True).data)

    @extend_schema(responses=BinderDetailSerializer)
    def retrieve(self, request, key=None):
        binder = get_binder(request.user, key)
        return Response(BinderDetailSerializer(binder_detail(binder)).data)

    def _run(self, call):
        try:
            return call()
        except MarketingAuthorization.DoesNotExist:
            raise Http404("AMM inconnue.")
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)

    @extend_schema(request=CheckInputSerializer, responses=BinderDetailSerializer)
    @action(detail=True, methods=["post"])
    def check(self, request, key=None):
        """Constat de l'archiviste sur une page : conforme, corrigé (valeurs lues) ou absent."""
        binder = get_binder(request.user, key)
        serializer = CheckInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self._run(
            lambda: actions.record_check(
                binder,
                data["amm"],
                result=data["result"],
                corrections=data["corrections"],
                note=data["note"],
                user=request.user,
            )
        )
        return Response(BinderDetailSerializer(binder_detail(binder)).data)

    @extend_schema(request=UncheckInputSerializer, responses=BinderDetailSerializer)
    @action(detail=True, methods=["post"])
    def uncheck(self, request, key=None):
        binder = get_binder(request.user, key)
        serializer = UncheckInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._run(
            lambda: actions.undo_check(binder, serializer.validated_data["amm"], user=request.user)
        )
        return Response(BinderDetailSerializer(binder_detail(binder)).data)

    @extend_schema(request=AddPageInputSerializer, responses={201: AddPageResultSerializer})
    @action(detail=True, methods=["post"])
    def pages(self, request, key=None):
        """Ajoute la page d'un produit oublié : l'AMM est créée dans le pays du classeur."""
        binder = get_binder(request.user, key)
        serializer = AddPageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amm, landing, created = self._run(
            lambda: actions.add_page(binder, user=request.user, **serializer.validated_data)
        )
        payload = {
            "amm_id": amm.pk,
            "binder_key": landing.key,
            "product_created": created,
            "binder": binder_detail(landing),
        }
        return Response(AddPageResultSerializer(payload).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request={"multipart/form-data": PageScanInputSerializer},
        responses={202: PageScanResultSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path=r"pages/(?P<amm_id>[0-9a-f-]{36})/scan",
        parser_classes=[MultiPartParser, FormParser, JSONParser],
    )
    def page_scan(self, request, key=None, amm_id=None):
        """Importe le scan d'une page : lu et rangé comme un import de dossier, sur cette AMM."""
        from apps.imports.dossier_views import _enqueue_analysis

        binder = get_binder(request.user, key)
        serializer = PageScanInputSerializer(data={"files": request.FILES.getlist("files")})
        serializer.is_valid(raise_exception=True)
        batch = self._run(
            lambda: actions.import_page_scan(
                binder, amm_id, files=serializer.validated_data["files"], user=request.user
            )
        )
        _enqueue_analysis(batch)
        batch.refresh_from_db()
        return Response(
            PageScanResultSerializer({"batch_id": batch.pk, "status": batch.status}).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @extend_schema(request=ExtraPageInputSerializer, responses={201: ExtraPageSerializer})
    @action(detail=True, methods=["post"], url_path="extras")
    def add_extra(self, request, key=None):
        """Dossier présent dans le classeur papier mais sans AMM dans l'application."""
        binder = get_binder(request.user, key)
        serializer = ExtraPageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        extra = actions.add_extra(binder, user=request.user, **serializer.validated_data)
        payload = {
            "id": extra.pk,
            "product_name": extra.product_name,
            "note": extra.note,
            "created_by": request.user.full_name,
            "created_at": extra.created_at,
        }
        return Response(ExtraPageSerializer(payload).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"extras/(?P<extra_id>[0-9a-f-]{36})")
    def remove_extra(self, request, key=None, extra_id=None):
        binder = get_binder(request.user, key)
        self._run(lambda: actions.remove_extra(binder, extra_id, user=request.user))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        responses={(200, "application/pdf"): OpenApiResponse(description="Classeur en PDF")}
    )
    @action(detail=True, methods=["get"])
    def pdf(self, request, key=None):
        """Le classeur page par page, comme à l'écran. Réservé au siège."""
        if not request.user.is_global:
            raise PermissionDenied("Le téléchargement des classeurs est réservé au siège.")
        binder = get_binder(request.user, key)
        content = binder_pdf(binder_detail(binder), generated_by=request.user.full_name)
        name = f"Classeur_{binder.key}_{today():%Y-%m-%d}.pdf"
        response = HttpResponse(content, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["Cache-Control"] = "private, no-store"
        return response

    # --- Classeur avec les décisions officielles (siège) --------------------------------------

    def _hq_binder(self, request, key):
        if not request.user.is_global:
            raise PermissionDenied("Le téléchargement des classeurs est réservé au siège.")
        return get_binder(request.user, key)

    @extend_schema(
        methods=["GET"],
        responses=BinderExportSerializer(many=True),
        description="Dernières préparations du classeur avec les décisions officielles.",
    )
    @extend_schema(
        methods=["POST"],
        request=None,
        responses={202: BinderExportSerializer},
        description="Lance la préparation (une seule à la fois par classeur).",
    )
    @action(detail=True, methods=["get", "post"])
    def exports(self, request, key=None):
        binder = self._hq_binder(request, key)
        if request.method == "GET":
            recent = BinderExport.objects.filter(binder_key=binder.key).select_related(
                "created_by"
            )[:3]
            return Response(BinderExportSerializer(recent, many=True).data)
        from .tasks import build_binder_export

        with transaction.atomic():
            active = (
                BinderExport.objects.select_for_update()
                .filter(binder_key=binder.key, status__in=BinderExport.ACTIVE)
                .first()
            )
            export = active or BinderExport.objects.create(
                country=binder.country, binder_key=binder.key, created_by=request.user
            )
            if active is None:
                enqueue(build_binder_export, str(export.pk))
        export.refresh_from_db()
        return Response(BinderExportSerializer(export).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        responses={(200, "application/pdf"): OpenApiResponse(description="Classeur complet")}
    )
    @action(detail=True, methods=["get"], url_path=r"exports/(?P<export_id>[0-9a-f-]{36})/file")
    def export_file(self, request, key=None, export_id=None):
        binder = self._hq_binder(request, key)
        export = BinderExport.objects.filter(
            pk=export_id, binder_key=binder.key, status=BinderExport.Status.READY
        ).first()
        if export is None or not export.file:
            raise Http404("Classeur pas encore prêt.")
        name = f"Classeur_{binder.key}_decisions_{export.finished_at:%Y-%m-%d}.pdf"
        open_stored_file(export.file)
        response = FileResponse(
            export.file, content_type="application/pdf", as_attachment=True, filename=name
        )
        response["Cache-Control"] = "private, no-store"
        return response
