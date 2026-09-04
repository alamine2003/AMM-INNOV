"""Document endpoints. The AMM/renewal/country/product routes are implemented as functions
called from the owning viewsets so that URLs match the specification."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import (
    CEO_ONLY,
    CountryScopedQuerysetMixin,
    RolePermission,
    ensure_country_in_scope,
)
from apps.amm.models import Renewal
from apps.amm.serializers import django_to_drf_validation_error

from .models import Document
from .serializers import (
    DocumentDetailSerializer,
    DocumentReplaceSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
)
from .services.archive import build_archive
from .services.ingest import archive_document, ingest_document


def _apply_common_filters(queryset, request):
    kind = request.query_params.get("kind")
    if kind:
        queryset = queryset.filter(kind__in=[k.strip().upper() for k in kind.split(",")])
    year = request.query_params.get("year")
    if year and year.isdigit():
        queryset = queryset.filter(document_date__year=int(year))
    include_archived = request.query_params.get("include_archived", "").lower() in {"1", "true"}
    if not include_archived:
        queryset = queryset.current()
    return queryset


def _group_by_period(amm, documents) -> list[dict]:
    """[{period: RENEWAL, sequence, label, documents}, ..., {period: ORIGINAL, ...}]."""
    by_renewal: dict = {}
    original: list = []
    for document in documents:
        if document.renewal_id:
            by_renewal.setdefault(document.renewal_id, []).append(document)
        else:
            original.append(document)
    groups = []
    for renewal in amm.renewals.order_by("-sequence"):
        groups.append(
            {
                "period": "RENEWAL",
                "sequence": renewal.sequence,
                "renewal_id": str(renewal.pk),
                "workflow_status": renewal.workflow_status,
                "label": f"Renouvellement {renewal.sequence}"
                + (f" — {renewal.number}" if renewal.number else ""),
                "start_date": renewal.start_date,
                "end_date": renewal.end_date,
                "documents": DocumentSerializer(by_renewal.get(renewal.pk, []), many=True).data,
            }
        )
    groups.append(
        {
            "period": "ORIGINAL",
            "sequence": 0,
            "renewal_id": None,
            "workflow_status": None,
            "label": "AMM d'origine" + (f" — {amm.original_number}" if amm.original_number else ""),
            "start_date": amm.original_start_date,
            "end_date": amm.original_end_date,
            "documents": DocumentSerializer(original, many=True).data,
        }
    )
    return groups


def _upload(request, amm, renewal=None):
    ensure_country_in_scope(request.user, amm.country)
    serializer = DocumentUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    if renewal is None and data.get("renewal"):
        renewal = get_object_or_404(Renewal, pk=data["renewal"], amm=amm)
    try:
        document = ingest_document(
            amm,
            data["file"],
            data["kind"],
            document_date=data.get("document_date"),
            title=data.get("title", ""),
            renewal=renewal,
            user=request.user,
        )
    except DjangoValidationError as exc:
        raise django_to_drf_validation_error(exc)
    return Response(DocumentDetailSerializer(document).data, status=status.HTTP_201_CREATED)


def amm_documents(request, amm):
    if request.method == "POST":
        return _upload(request, amm)
    queryset = _apply_common_filters(
        Document.objects.filter(amm=amm).select_related("renewal", "amm__country", "amm__product"),
        request,
    )
    if request.query_params.get("group") == "period":
        return Response(_group_by_period(amm, list(queryset)))
    return Response(DocumentSerializer(queryset, many=True).data)


def renewal_documents(request, renewal):
    return _upload(request, renewal.amm, renewal=renewal)


def amm_documents_archive(request, amm):
    queryset = _apply_common_filters(
        Document.objects.filter(amm=amm).select_related("amm__country", "amm__product"), request
    )
    payload = build_archive(list(queryset))
    response = HttpResponse(payload, content_type="application/zip")
    response["Content-Disposition"] = (
        f'attachment; filename="{amm.country.iso2}_{amm.product.slug.upper()}_documents.zip"'
    )
    return response


def _library(request, queryset):
    queryset = _apply_common_filters(
        queryset.select_related("renewal", "amm__country", "amm__product"), request
    )
    from apps.core.pagination import StandardPagination

    paginator = StandardPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(DocumentSerializer(page, many=True).data)


def country_documents(request, country):
    ensure_country_in_scope(request.user, country)
    return _library(request, Document.objects.filter(amm__country=country))


def product_documents(request, product):
    queryset = Document.objects.filter(amm__product=product)
    if not request.user.is_global:
        queryset = queryset.filter(amm__country__in=request.user.countries.all())
    return _library(request, queryset)


class DocumentViewSet(
    CountryScopedQuerysetMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Document.objects.select_related(
        "amm", "amm__country", "amm__product", "renewal", "uploaded_by", "replaces"
    )
    serializer_class = DocumentDetailSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    delete_roles = CEO_ONLY
    parser_classes = [MultiPartParser, FormParser]
    country_lookup = "amm__country"
    filterset_fields = {
        "kind": ["exact", "in"],
        "amm": ["exact"],
        "amm__country__iso2": ["exact"],
        "amm__product": ["exact"],
        "is_current": ["exact"],
        "document_date": ["year", "gte", "lte"],
    }
    search_fields = ["title", "amm__product__name", "amm__original_number"]
    ordering_fields = ["document_date", "uploaded_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            include_archived = self.request.query_params.get("include_archived", "").lower()
            if include_archived not in {"1", "true"}:
                queryset = queryset.current()
        return queryset

    def get_serializer_class(self):
        return DocumentSerializer if self.action == "list" else DocumentDetailSerializer

    @extend_schema(responses={(200, "application/pdf"): bytes})
    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        document = self.get_object()
        download = request.query_params.get("download", "").lower() in {"1", "true"}
        document.file.open("rb")
        response = FileResponse(
            document.file,
            content_type=document.content_type,
            as_attachment=download,
            filename=document.export_filename(),
        )
        response["Cache-Control"] = "private, max-age=300"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    @extend_schema(request=DocumentReplaceSerializer, responses={201: DocumentDetailSerializer})
    @action(detail=True, methods=["post"])
    def replace(self, request, pk=None):
        previous = self.get_object()
        ensure_country_in_scope(request.user, previous.amm.country)
        if not previous.is_current or previous.is_archived:
            raise PermissionDenied("Seule la version courante d'un document peut être remplacée.")
        serializer = DocumentReplaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            document = ingest_document(
                previous.amm,
                data["file"],
                previous.kind,
                document_date=data.get("document_date") or previous.document_date,
                title=data.get("title") or previous.title,
                renewal=previous.renewal,
                user=request.user,
                replaces=previous,
            )
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)
        return Response(DocumentDetailSerializer(document).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        archive_document(instance, user=self.request.user)
