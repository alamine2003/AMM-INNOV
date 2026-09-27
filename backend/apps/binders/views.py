"""Classeurs d'archivage : l'étagère, un classeur, et le constat de l'archiviste page par page.

Un réglementaire pays ne voit que les classeurs de ses pays ; le siège voit tout et peut
télécharger chaque classeur en PDF, tel qu'il apparaît à l'écran.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.amm.models import MarketingAuthorization
from apps.amm.serializers import django_to_drf_validation_error
from apps.core.dates import today

from . import actions
from .layout import binder_detail, get_binder, shelf
from .pdf import binder_pdf
from .serializers import (
    BinderDetailSerializer,
    BinderSummarySerializer,
    CheckInputSerializer,
    ExtraPageInputSerializer,
    ExtraPageSerializer,
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
