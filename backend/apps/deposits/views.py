"""Rubrique « Dépôt AMM » : dossiers de renouvellement, du montage au siège à la décision.

Le siège voit tous les dossiers, les monte et les envoie ; un réglementaire pays ne voit que ceux
de ses pays, les télécharge, enregistre le dépôt, les commissions et la décision.
"""

import itertools
import logging
from datetime import timedelta

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.handlers.asgi import ASGIRequest
from django.db import connection
from django.db.models import Exists, OuterRef, Prefetch
from django.http import FileResponse, Http404, StreamingHttpResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.permissions import GLOBAL_ROLES, RolePermission
from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.serializers import django_to_drf_validation_error
from apps.core.dates import today
from apps.core.exceptions import StorageUnavailable
from apps.documents.services.archive import aiter_blocks, iter_zip
from apps.documents.views import open_stored_file

from . import actions, bundle
from .models import DepositDossier, DepositMessage, PieceType
from .serializers import (
    AbandonSerializer,
    DecisionInputSerializer,
    DepositDetailSerializer,
    DepositInputSerializer,
    DepositSummarySerializer,
    EventInputSerializer,
    MessageInputSerializer,
    OpenDossierSerializer,
    PieceTypeSerializer,
    PieceUploadSerializer,
    SampleInputSerializer,
    SamplesRequiredSerializer,
    SendSerializer,
    SuggestionSerializer,
)

logger = logging.getLogger(__name__)
FILE_RESPONSE = OpenApiResponse(description="Pièce")


def _run(call):
    try:
        return call()
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc))
    except DjangoValidationError as exc:
        raise django_to_drf_validation_error(exc)


class DepositViewSet(viewsets.ViewSet):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def _queryset(self):
        return actions.visible_dossiers(self.request.user).prefetch_related(
            "pieces",
            "samples",
            "events__created_by",
            Prefetch("messages", queryset=DepositMessage.objects.select_related("author")),
        )

    def _get(self, pk) -> DepositDossier:
        try:
            return self._queryset().select_related("attestation").get(pk=pk)
        except (DepositDossier.DoesNotExist, DjangoValidationError, ValueError):
            raise Http404("Dossier de dépôt inconnu.")

    def _detail(self, pk, code=status.HTTP_200_OK):
        dossier = self._get(pk)
        return Response(
            DepositDetailSerializer(dossier, context={"request": self.request}).data, status=code
        )

    @extend_schema(responses=DepositSummarySerializer(many=True))
    def list(self, request):
        queryset = self._queryset().select_related("renewal__amm__product__range")
        country = request.query_params.get("country")
        if country:
            queryset = queryset.filter(renewal__amm__country__iso2=country.upper())
        return Response(
            DepositSummarySerializer(queryset, many=True, context={"request": request}).data
        )

    @extend_schema(responses=DepositDetailSerializer)
    def retrieve(self, request, pk=None):
        return self._detail(pk)

    @extend_schema(request=OpenDossierSerializer, responses={201: DepositDetailSerializer})
    def create(self, request):
        data = OpenDossierSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            amm = MarketingAuthorization.objects.select_related("country", "product").get(
                pk=data.validated_data["amm"]
            )
        except MarketingAuthorization.DoesNotExist:
            raise Http404("AMM inconnue.")
        dossier = _run(lambda: actions.open_dossier(amm, request.user))
        return self._detail(dossier.pk, status.HTTP_201_CREATED)

    @extend_schema(responses=SuggestionSerializer(many=True))
    @action(detail=False, methods=["get"])
    def suggestions(self, request):
        """AMM à renouveler dans l'année (ou expirées depuis moins d'un an), sans dossier."""
        in_progress = DepositDossier.objects.filter(
            renewal__amm=OuterRef("pk"), renewal__workflow_status__in=Renewal.OPEN_STATUSES
        )
        pending = Renewal.objects.filter(
            amm=OuterRef("pk"), workflow_status__in=Renewal.PENDING_STATUSES
        )
        queryset = (
            MarketingAuthorization.objects.select_related("product__range", "country")
            .filter(effective_end_date__isnull=False)
            .filter(effective_end_date__lte=today() + timedelta(days=365))
            # Une AMM expirée depuis plus d'un an ne se renouvelle plus : nouvelle demande d'AMM.
            .filter(effective_end_date__gte=today() - timedelta(days=365))
            .exclude(Exists(in_progress))
            .exclude(Exists(pending))
            .order_by("effective_end_date")
        )
        if not request.user.is_global:
            queryset = queryset.filter(country__in=request.user.countries.all())
        rows = list(queryset[:200])
        open_status = dict(
            Renewal.objects.filter(amm__in=rows, workflow_status__in=Renewal.OPEN_STATUSES)
            .order_by("sequence")
            .values_list("amm_id", "workflow_status")
        )
        for amm in rows:
            amm.renewal_status = open_status.get(amm.pk)
        return Response(SuggestionSerializer(rows, many=True).data)

    # --- Montage --------------------------------------------------------------------------

    @extend_schema(request=PieceUploadSerializer, responses={201: DepositDetailSerializer})
    @action(detail=True, methods=["post"])
    def pieces(self, request, pk=None):
        dossier = self._get(pk)
        data = PieceUploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        piece_type = None
        if data.validated_data.get("piece_type"):
            piece_type = PieceType.objects.filter(pk=data.validated_data["piece_type"]).first()
            if piece_type is None:
                raise Http404("Pièce inconnue.")
        _run(
            lambda: actions.add_piece(
                dossier,
                request.user,
                data.validated_data["file"],
                piece_type=piece_type,
                label=data.validated_data.get("label", ""),
            )
        )
        return self._detail(pk, status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=DepositDetailSerializer)
    @action(detail=True, methods=["delete"], url_path=r"pieces/(?P<piece_id>[0-9a-f-]+)")
    def remove_piece(self, request, pk=None, piece_id=None):
        dossier = self._get(pk)
        piece = dossier.pieces.filter(pk=piece_id).first()
        if piece is None:
            raise Http404("Pièce inconnue.")
        _run(lambda: actions.remove_piece(piece, request.user))
        return self._detail(pk)

    @extend_schema(
        responses={(200, "application/octet-stream"): OpenApiResponse(description="Pièce")}
    )
    @action(detail=True, methods=["get"], url_path=r"pieces/(?P<piece_id>[0-9a-f-]+)/file")
    def piece_file(self, request, pk=None, piece_id=None):
        dossier = self._get(pk)
        piece = dossier.pieces.filter(pk=piece_id).first()
        if piece is None:
            raise Http404("Pièce inconnue.")
        open_stored_file(piece.file)
        return FileResponse(
            piece.file,
            content_type=piece.content_type or "application/octet-stream",
            as_attachment=True,
            filename=piece.filename,
        )

    @extend_schema(request=SampleInputSerializer, responses={201: DepositDetailSerializer})
    @action(detail=True, methods=["post"])
    def samples(self, request, pk=None):
        dossier = self._get(pk)
        data = SampleInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(lambda: actions.add_sample(dossier, request.user, **data.validated_data))
        return self._detail(pk, status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=DepositDetailSerializer)
    @action(detail=True, methods=["delete"], url_path=r"samples/(?P<sample_id>[0-9a-f-]+)")
    def remove_sample(self, request, pk=None, sample_id=None):
        dossier = self._get(pk)
        sample = dossier.samples.filter(pk=sample_id).first()
        if sample is None:
            raise Http404("Échantillon inconnu.")
        _run(lambda: actions.remove_sample(sample, request.user))
        return self._detail(pk)

    @extend_schema(request=SamplesRequiredSerializer, responses=DepositDetailSerializer)
    @action(detail=True, methods=["post"], url_path="samples-required")
    def samples_required(self, request, pk=None):
        dossier = self._get(pk)
        data = SamplesRequiredSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(
            lambda: actions.set_samples_required(
                dossier, request.user, data.validated_data["required"]
            )
        )
        return self._detail(pk)

    # --- Envoi, téléchargement ------------------------------------------------------------

    @extend_schema(request=SendSerializer, responses=DepositDetailSerializer)
    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        dossier = self._get(pk)
        data = SendSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(lambda: actions.send(dossier, request.user, data.validated_data.get("note", "")))
        return self._detail(pk)

    @extend_schema(responses={(200, "application/zip"): OpenApiResponse(description="Dossier")})
    @action(detail=True, methods=["get"])
    def archive(self, request, pk=None):
        """Le dossier complet (ZIP) : bordereau puis pièces, dans l'ordre de la liste."""
        dossier = self._get(pk)
        if not dossier.sent_at and not request.user.is_global:
            raise PermissionDenied("Le siège n'a pas encore envoyé ce dossier.")
        actions.record_download(dossier, request.user)
        name = bundle.zip_name(dossier)
        entries = list(bundle.entries(dossier))
        if not connection.in_atomic_block:
            connection.close()  # la lecture des pièces ne tient pas de connexion du pool
        stream = iter_zip(entries)
        try:
            first = next(stream)
        except StopIteration:
            first = b""
        except Exception as exc:
            logger.warning("Dossier de dépôt %s : archive impossible (%s)", pk, exc)
            raise StorageUnavailable() from exc
        if isinstance(getattr(request, "_request", request), ASGIRequest):
            content = aiter_blocks(first, stream)
        else:
            content = itertools.chain([first], stream)
        response = StreamingHttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["Cache-Control"] = "private, no-store"
        return response

    # --- Pays : dépôt, suivi, décision ----------------------------------------------------

    @extend_schema(request=DepositInputSerializer, responses=DepositDetailSerializer)
    @action(detail=True, methods=["post"])
    def deposit(self, request, pk=None):
        dossier = self._get(pk)
        data = DepositInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(
            lambda: actions.record_deposit(
                dossier,
                request.user,
                data.validated_data["filing_date"],
                data.validated_data["file"],
            )
        )
        return self._detail(pk)

    @extend_schema(request=EventInputSerializer, responses={201: DepositDetailSerializer})
    @action(detail=True, methods=["post"])
    def events(self, request, pk=None):
        dossier = self._get(pk)
        data = EventInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        _run(
            lambda: actions.add_event(
                dossier,
                request.user,
                values["kind"],
                values["date"],
                values.get("note", ""),
                values.get("file"),
            )
        )
        return self._detail(pk, status.HTTP_201_CREATED)

    @extend_schema(
        responses={(200, "application/octet-stream"): OpenApiResponse(description="Pièce")}
    )
    @action(detail=True, methods=["get"], url_path=r"events/(?P<event_id>[0-9a-f-]+)/file")
    def event_file(self, request, pk=None, event_id=None):
        dossier = self._get(pk)
        event = dossier.events.filter(pk=event_id).first()
        if event is None or not event.file:
            raise Http404("Pièce inconnue.")
        open_stored_file(event.file)
        return FileResponse(event.file, as_attachment=True, filename=event.filename)

    @extend_schema(request=DecisionInputSerializer, responses=DepositDetailSerializer)
    @action(detail=True, methods=["post"])
    def decision(self, request, pk=None):
        dossier = self._get(pk)
        data = DecisionInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        _run(
            lambda: actions.record_decision(
                dossier,
                request.user,
                values["result"],
                values["decision_date"],
                number=values.get("number", ""),
                start_date=values.get("start_date"),
                note=values.get("note", ""),
                file=values.get("file"),
            )
        )
        return self._detail(pk)

    @extend_schema(request=AbandonSerializer, responses=DepositDetailSerializer)
    @action(detail=True, methods=["post"])
    def abandon(self, request, pk=None):
        dossier = self._get(pk)
        data = AbandonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(lambda: actions.abandon(dossier, request.user, data.validated_data["reason"]))
        return self._detail(pk)

    @extend_schema(request=MessageInputSerializer, responses={201: DepositDetailSerializer})
    @action(detail=True, methods=["post"])
    def messages(self, request, pk=None):
        dossier = self._get(pk)
        data = MessageInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        _run(lambda: actions.post_message(dossier, request.user, data.validated_data["body"]))
        return self._detail(pk, status.HTTP_201_CREATED)


class PieceTypeViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Pièces demandées : liste de base et ajustements par pays (le siège les modifie)."""

    serializer_class = PieceTypeSerializer
    permission_classes = [RolePermission]
    write_roles = GLOBAL_ROLES
    pagination_class = None
    queryset = (
        PieceType.objects.select_related("country")
        .prefetch_related("excluded_countries")
        .order_by("country__name", "order", "label")
    )

    def perform_destroy(self, instance):
        # Une pièce déjà jointe à des dossiers est désactivée : les dossiers la gardent.
        from .models import DepositPiece

        if DepositPiece.objects.filter(piece_type=instance).exists():
            instance.active = False
            instance.save(update_fields=["active"])
        else:
            instance.delete()
