"""Authenticated folder intake, asynchronous preview and explicit atomic confirmation."""

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

from apps.accounts.permissions import RolePermission, ensure_country_in_scope
from apps.amm.serializers import django_to_drf_validation_error
from apps.catalog.models import Country
from apps.core.tasks import enqueue

from .dossier.application import StalePreview, apply_dossier
from .dossier.upload import stage_dossier
from .dossier_serializers import (
    DossierAnalyzeSerializer,
    DossierConfirmSerializer,
    DossierFileRequestSerializer,
    DossierImportSerializer,
    DossierUploadSerializer,
)
from .models import DossierImport
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


class DossierImportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = DossierImport.objects.select_related("created_by", "country").prefetch_related(
        "files",
        "audit__user",
        "audit__proof_file",
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
            )
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)
        _enqueue_analysis(batch)
        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_202_ACCEPTED)

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
                accepted_changes=serializer.validated_data["accepted_changes"],
            )
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)
        return Response(self.get_serializer(batch).data)

    @extend_schema(
        parameters=[DossierFileRequestSerializer], responses={(200, "application/pdf"): bytes}
    )
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        batch = self.get_object()
        params = DossierFileRequestSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        source = get_object_or_404(batch.files.all(), pk=params.validated_data["file_id"])
        response = FileResponse(
            source.file.open("rb"),
            content_type=source.content_type,
            filename=source.relative_path.rsplit("/", 1)[-1],
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox"
        return response
