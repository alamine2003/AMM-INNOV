from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Prefetch
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import (
    CountryScopedQuerysetMixin,
    RolePermission,
    ensure_country_in_scope,
)
from apps.documents.models import Document

from .filters import AmmFilter, RenewalFilter
from .history import amm_history
from .models import MarketingAuthorization, Renewal
from .serializers import (
    AmmDetailSerializer,
    AmmListSerializer,
    HistoryEntrySerializer,
    RenewalSerializer,
    RenewalTransitionSerializer,
    django_to_drf_validation_error,
)
from .services import workflow


def amm_base_queryset():
    current_scan = Document.objects.filter(
        amm=OuterRef("pk"), kind=Document.Kind.AMM, is_current=True, archived_at__isnull=True
    )
    return (
        MarketingAuthorization.objects.select_related(
            "product", "product__range", "country", "owner"
        )
        .prefetch_related(Prefetch("renewals", queryset=Renewal.objects.order_by("sequence")))
        .annotate(has_current_scan=Exists(current_scan))
    )


class AmmViewSet(CountryScopedQuerysetMixin, viewsets.ModelViewSet):
    queryset = amm_base_queryset()
    permission_classes = [IsAuthenticated, RolePermission]
    filterset_class = AmmFilter
    search_fields = [
        "product__name",
        "product__aliases__raw_name",
        "original_number",
        "renewals__number",
        "country__name",
    ]
    ordering_fields = [
        "effective_end_date",
        "filing_deadline",
        "status",
        "urgency",
        "product__name",
        "country__iso2",
        "original_start_date",
        "updated_at",
    ]
    ordering = ["effective_end_date", "product__name"]
    country_lookup = "country"

    def get_serializer_class(self):
        if self.action in ("retrieve", "create", "update", "partial_update"):
            return AmmDetailSerializer
        return AmmListSerializer

    def get_queryset(self):
        return super().get_queryset().distinct()

    def perform_create(self, serializer):
        ensure_country_in_scope(self.request.user, serializer.validated_data.get("country"))
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:  # deux créations simultanées du même produit × pays
            raise serializers.ValidationError(
                {"detail": "Une AMM existe déjà pour ce produit dans ce pays."}
            )

    @extend_schema(responses=HistoryEntrySerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        amm = self.get_object()
        return Response(HistoryEntrySerializer(amm_history(amm), many=True).data)

    @extend_schema(
        request=RenewalSerializer,
        responses={200: RenewalSerializer(many=True), 201: RenewalSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def renewals(self, request, pk=None):
        amm = self.get_object()
        if request.method == "GET":
            queryset = amm.renewals.order_by("-sequence")
            return Response(RenewalSerializer(queryset, many=True).data)
        serializer = RenewalSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        renewal = serializer.save(amm=amm)
        renewal.refresh_from_db()
        return Response(RenewalSerializer(renewal).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter("group", str, description="`period` pour grouper par période"),
            OpenApiParameter("kind", str),
            OpenApiParameter("include_archived", bool),
        ],
        responses={200: dict},
    )
    @action(detail=True, methods=["get", "post"], url_path="documents")
    def documents(self, request, pk=None):
        from apps.documents.views import amm_documents

        return amm_documents(request, self.get_object())

    @extend_schema(responses={(200, "application/zip"): bytes})
    @action(detail=True, methods=["get"], url_path=r"documents/archive\.zip")
    def documents_archive(self, request, pk=None):
        from apps.documents.views import amm_documents_archive

        return amm_documents_archive(request, self.get_object())


class RenewalViewSet(
    CountryScopedQuerysetMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Renewal.objects.select_related("amm", "amm__country", "amm__product")
    serializer_class = RenewalSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    filterset_class = RenewalFilter
    ordering_fields = ["sequence", "filing_date", "start_date", "end_date", "updated_at"]
    country_lookup = "amm__country"

    @extend_schema(request=RenewalTransitionSerializer, responses=RenewalSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        renewal = self.get_object()
        serializer = RenewalTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        to = data.pop("to")
        try:
            renewal = workflow.transition(renewal, to, actor=request.user, **data)
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)
        renewal.refresh_from_db()
        return Response(RenewalSerializer(renewal).data)

    @extend_schema(responses={201: dict})
    @action(detail=True, methods=["post"], url_path="documents")
    def documents(self, request, pk=None):
        from apps.documents.views import renewal_documents

        return renewal_documents(request, self.get_object())
