"""Dépôt d'un dossier, lecture asynchrone et rangement automatique ; question « quelle AMM ? » ;
points à vérifier plus tard (appliquer la valeur du scan / ignorer)."""

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import (
    CountryScopedQuerysetMixin,
    RolePermission,
    ensure_country_in_scope,
)
from apps.amm.models import MarketingAuthorization
from apps.amm.serializers import django_to_drf_validation_error
from apps.catalog.models import Country
from apps.core.exceptions import StoredFileLost
from apps.core.tasks import enqueue
from apps.documents.views import file_is_missing, open_stored_file

from .dossier.application import StalePreview, apply_dossier
from .dossier.review_points import apply_point, ignore_point
from .dossier.upload import reusable_files, stage_dossier
from .dossier_serializers import (
    DossierAnalyzeSerializer,
    DossierChooseAmmSerializer,
    DossierConfirmSerializer,
    DossierFileRequestSerializer,
    DossierImportSerializer,
    DossierKnownFilesSerializer,
    DossierReviewPointSerializer,
    DossierUploadSerializer,
)
from .models import DossierImport, DossierReviewPoint
from .tasks import analyze_dossier

logger = logging.getLogger(__name__)


def _enqueue_analysis(batch):
    try:
        enqueue(analyze_dossier, str(batch.pk))
    except Exception:
        logger.exception("Échec de lancement de l'analyse du dossier %s", batch.pk)
        DossierImport.objects.filter(pk=batch.pk, status=DossierImport.Status.PENDING).update(
            status=DossierImport.Status.FAILED,
            error="Le service d'analyse est indisponible. Vous pouvez relancer l'analyse.",
        )


def serve_dossier_file(source):
    """Diffuse un scan déposé depuis le stockage par défaut (disque ou S3/R2).

    Le scan d'origine perdu (lot déposé avant le stockage permanent) mais déjà rangé dans la
    fiche : on diffuse la copie rangée. Sinon, 410 « fichier perdu » plutôt qu'une erreur 503.
    """
    stored, content_type = source.file, source.content_type
    document = source.document
    if document is not None and file_is_missing(stored):
        stored, content_type = document.file, document.content_type
    try:
        open_stored_file(stored)
    except StoredFileLost:
        if document is None or stored is document.file:
            raise
        open_stored_file(document.file)
        stored, content_type = document.file, document.content_type
    response = FileResponse(
        stored,
        content_type=content_type,
        filename=source.relative_path.rsplit("/", 1)[-1],
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "sandbox"
    return response


class DossierImportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = DossierImport.objects.select_related("created_by", "country").prefetch_related(
        "files",
        "audit__user",
        "audit__proof_file",
        "review_points__proof_file",
        "review_points__resolved_by",
    )
    serializer_class = DossierImportSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_global:
            queryset = queryset.filter(created_by=user).filter(
                Q(country__isnull=True) | Q(country__in=user.countries.all())
            )
        return queryset

    @extend_schema(request=DossierUploadSerializer, responses={202: DossierImportSerializer})
    def create(self, request):
        serializer = DossierUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            batch = stage_dossier(
                uploads=data["files"],
                paths=data["paths"],
                root_name=data["root_name"],
                user=request.user,
                reused=data["reused"],
            )
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)
        _enqueue_analysis(batch)
        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=DossierKnownFilesSerializer, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="known-files")
    def known_files(self, request):
        """Empreintes déjà envoyées par l'utilisateur : ces fichiers n'ont pas à être renvoyés."""
        params = DossierKnownFilesSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        known = reusable_files(request.user, params.validated_data["sha256"])
        return Response({"known": sorted(known)})

    @extend_schema(request=DossierAnalyzeSerializer, responses={202: DossierImportSerializer})
    @action(detail=True, methods=["post"])
    def analyze(self, request, pk=None):
        self.get_object()
        params = DossierAnalyzeSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        iso2 = (params.validated_data.get("country") or "").strip().upper()
        country = get_object_or_404(Country, iso2=iso2) if iso2 else None
        if country is not None:
            ensure_country_in_scope(request.user, country)
        with transaction.atomic():
            batch = DossierImport.objects.select_for_update().get(pk=pk)
            if batch.status in {DossierImport.Status.RUNNING, DossierImport.Status.APPLIED}:
                raise StalePreview("Ce dossier est en cours d'analyse ou déjà enregistré.")
            if country is not None:
                batch.country = country
            batch.status = DossierImport.Status.PENDING
            batch.preview_token = ""
            batch.error = ""
            batch.save(update_fields=["country", "status", "preview_token", "error"])
        _enqueue_analysis(batch)
        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(request=DossierConfirmSerializer, responses=DossierImportSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        self.get_object()
        serializer = DossierConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            batch = apply_dossier(
                pk,
                user=request.user,
                token=serializer.validated_data["preview_token"],
                create=serializer.validated_data["create_amm"],
            )
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)
        return Response(self.get_serializer(batch).data)

    @extend_schema(request=DossierChooseAmmSerializer, responses={202: DossierImportSerializer})
    @action(detail=True, methods=["post"], url_path="choose-amm")
    def choose_amm(self, request, pk=None):
        """« Ranger les documents ici » : l'AMM choisie, le dossier est relu puis rangé."""
        self.get_object()
        params = DossierChooseAmmSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        amm = get_object_or_404(
            MarketingAuthorization.objects.select_related("country"),
            pk=params.validated_data["amm_id"],
        )
        ensure_country_in_scope(request.user, amm.country)
        with transaction.atomic():
            batch = DossierImport.objects.select_for_update().get(pk=pk)
            if batch.status in {DossierImport.Status.RUNNING, DossierImport.Status.APPLIED}:
                raise StalePreview("Ce dossier est en cours d'analyse ou déjà rangé.")
            batch.amm = amm
            batch.country = amm.country
            batch.status = DossierImport.Status.PENDING
            batch.preview_token = ""
            batch.error = ""
            batch.save(update_fields=["amm", "country", "status", "preview_token", "error"])
        _enqueue_analysis(batch)
        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        parameters=[DossierFileRequestSerializer],
        responses={(200, "application/pdf"): bytes, 410: None},
    )
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        batch = self.get_object()
        params = DossierFileRequestSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        source = get_object_or_404(
            batch.files.select_related("document"), pk=params.validated_data["file_id"]
        )
        return serve_dossier_file(source)


class DossierReviewPointViewSet(
    CountryScopedQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Points à vérifier plus tard, par AMM ou par lot, dans le périmètre de l'utilisateur."""

    queryset = DossierReviewPoint.objects.select_related(
        "batch", "proof_file", "resolved_by", "amm__country"
    )
    serializer_class = DossierReviewPointSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    country_lookup = "amm__country"
    pagination_class = None

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if self.action == "list":
            for key, lookup in (("amm", "amm_id"), ("batch", "batch_id")):
                if params.get(key):
                    queryset = queryset.filter(**{lookup: params[key]})
            if params.get("status"):
                queryset = queryset.filter(status=params["status"].upper())
        return queryset

    def _resolve(self, request, handler):
        point = self.get_object()
        try:
            point = handler(point.pk, user=request.user)
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)
        return Response(self.get_serializer(self.get_queryset().get(pk=point.pk)).data)

    @extend_schema(request=None, responses=DossierReviewPointSerializer)
    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        """« Appliquer la valeur du scan » : remplace la valeur de la fiche (audit, recalcul)."""
        return self._resolve(request, apply_point)

    @extend_schema(request=None, responses=DossierReviewPointSerializer)
    @action(detail=True, methods=["post"])
    def ignore(self, request, pk=None):
        """« Ignorer » : la fiche reste telle quelle, le point est fermé."""
        return self._resolve(request, ignore_point)

    @extend_schema(responses={(200, "application/pdf"): bytes, 410: None})
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        """Le scan de preuve du point (réglementaires du pays compris, sans accès au lot)."""
        point = self.get_object()
        if point.proof_file_id is None:
            raise StoredFileLost("Ce point n'a pas de scan associé.")
        source = (
            type(point.proof_file).objects.select_related("document").get(pk=point.proof_file_id)
        )
        return serve_dossier_file(source)
