from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef, Prefetch
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import (
    CountryScopedQuerysetMixin,
    RolePermission,
    ensure_country_in_scope,
)
from apps.core.trash import IdempotentDestroyMixin, TrashDestroyMixin
from apps.documents.models import Document

from .extensions import list_annotations
from .filters import AmmFilter, RenewalFilter
from .history import amm_history
from .models import MarketingAuthorization, Renewal
from .serializers import (
    ActionPlanSerializer,
    AmmDetailSerializer,
    AmmListSerializer,
    HistoryEntrySerializer,
    RenewalSerializer,
    RenewalTransitionSerializer,
    django_to_drf_validation_error,
)
from .services import workflow
from .services.gaps import GAPS, with_gaps
from .services.priority import by_urgency
from .services.sequence import resequence
from .services.status import apply_state
from .services.workflow import lock_amm


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


class AmmViewSet(TrashDestroyMixin, CountryScopedQuerysetMixin, viewsets.ModelViewSet):
    # Supprimer une fiche la met à la corbeille, avec ses imports de dossiers (restaurables).
    trash_include_protected = True

    def trash_country(self, instance) -> str:
        return instance.country.iso2

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
        "ideal_filing_date",
        "agency_filing_deadline",
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
        # Colonnes calculées par d'autres apps (points à vérifier des imports de dossiers) :
        # ajoutées à la requête, pas au module, pour qu'elles soient déjà déclarées.
        return super().get_queryset().annotate(**list_annotations()).distinct()

    def perform_create(self, serializer):
        ensure_country_in_scope(self.request.user, serializer.validated_data.get("country"))
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:  # deux créations simultanées du même produit × pays
            raise serializers.ValidationError(
                {"detail": "Une AMM existe déjà pour ce produit dans ce pays."}
            )

    def update(self, request, *args, **kwargs):
        # Modification atomique, ligne verrouillée avant d'être relue (campagne de chaos s15c,
        # H6) : l'UPDATE, l'entrée d'historique et la réconciliation des alertes partaient en
        # autocommit (un crash entre deux laissait une modification sans trace d'audit), et deux
        # éditeurs simultanés s'écrasaient : chacun relisait la ligne avant l'autre puis
        # réécrivait tous ses champs.
        with transaction.atomic():
            lock_amm(kwargs[self.lookup_url_kwarg or self.lookup_field])
            return super().update(request, *args, **kwargs)

    @extend_schema(
        responses=ActionPlanSerializer,
        parameters=[
            OpenApiParameter("limit", int, required=False, description="AMM par manque (10)."),
        ],
        description=(
            "Plan d'action : les AMM à compléter, par manque (origine non identifiée, sans "
            "renouvellement, renouvellement à déposer, scans absents), les plus urgentes "
            "d'abord. Accepte les filtres de la liste (pays, gamme…)."
        ),
    )
    @action(detail=False, methods=["get"], url_path="action-plan")
    def action_plan(self, request):
        try:
            limit = max(1, min(int(request.query_params.get("limit", 10)), 50))
        except ValueError:
            limit = 10
        base = self.filter_queryset(
            CountryScopedQuerysetMixin.get_queryset(self).select_related("product", "country")
        )
        ids = base.order_by().values("pk")
        scope = MarketingAuthorization.objects.filter(pk__in=ids).select_related(
            "product", "country"
        )
        categories = []
        for gap, text in GAPS.items():
            matching = with_gaps(scope, [gap])
            items = by_urgency(matching)[:limit]
            categories.append(
                {
                    "gap": gap,
                    **text,
                    "count": matching.count(),
                    "items": [
                        {
                            "id": amm.pk,
                            "product_name": amm.product.name,
                            "country_iso2": amm.country.iso2,
                            "country_name": amm.country.name,
                            "status": amm.status,
                            "effective_end_date": amm.effective_end_date,
                            "original_number": amm.original_number,
                            "original_start_date": amm.original_start_date,
                        }
                        for amm in items
                    ],
                }
            )
        total = with_gaps(scope, list(GAPS)).count()
        return Response(ActionPlanSerializer({"total": total, "categories": categories}).data)

    @extend_schema(responses=HistoryEntrySerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        amm = self.get_object()
        return Response(HistoryEntrySerializer(amm_history(amm), many=True).data)

    @extend_schema(methods=["GET"], responses=RenewalSerializer(many=True))
    @extend_schema(
        methods=["POST"],
        request=RenewalSerializer,
        responses={
            201: RenewalSerializer,
            200: OpenApiResponse(
                RenewalSerializer,
                description="Même décision déjà enregistrée : le renouvellement existant.",
            ),
        },
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
        replayed = getattr(renewal, "_replayed", False)
        renewal.refresh_from_db()
        # La même décision renvoyée (double clic, relance après un délai dépassé) : 200 et le
        # renouvellement existant, au lieu d'un doublon (s02b, s15a).
        code = status.HTTP_200_OK if replayed else status.HTTP_201_CREATED
        return Response(RenewalSerializer(renewal).data, status=code)

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
    IdempotentDestroyMixin,
    CountryScopedQuerysetMixin,
    viewsets.mixins.RetrieveModelMixin,
    viewsets.mixins.UpdateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Renouvellements des AMM, limités aux pays de l'utilisateur. Annuler le dernier
    renouvellement le met à la corbeille ; l'annuler une deuxième fois ne fait rien."""

    queryset = Renewal.objects.select_related("amm", "amm__country", "amm__product")
    serializer_class = RenewalSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    filterset_class = RenewalFilter
    ordering_fields = ["sequence", "filing_date", "start_date", "end_date", "updated_at"]
    country_lookup = "amm__country"

    def update(self, request, *args, **kwargs):
        # Même ordre de verrouillage que le workflow (AMM puis renouvellement) : atomique, sans
        # mise à jour perdue ni interblocage avec une décision enregistrée en même temps.
        with transaction.atomic():
            try:
                amm_id = (
                    Renewal.objects.filter(pk=kwargs[self.lookup_url_kwarg or self.lookup_field])
                    .values_list("amm_id", flat=True)
                    .first()
                )
            except (ValueError, DjangoValidationError):  # identifiant mal formé : 404 ci-dessous
                amm_id = None
            if amm_id is not None:
                lock_amm(amm_id)
            return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        """Correction d'un renouvellement (n°, dates) : ordre et état de l'AMM recalculés."""
        renewal = serializer.save()
        if resequence(renewal.amm):
            apply_state(renewal.amm)  # le dernier obtenu a pu changer : échéance et statut

    def perform_destroy(self, instance):
        """Annule le dernier renouvellement : l'AMM est recalculée, ses scans sont archivés."""
        try:
            self.trash_entry = workflow.delete_renewal(instance, actor=self.request.user)
        except DjangoValidationError as exc:
            raise django_to_drf_validation_error(exc)

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
