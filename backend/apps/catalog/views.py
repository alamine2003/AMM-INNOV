from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import CEO_ONLY, GLOBAL_ROLES, RolePermission

from .models import Country, Product, ProductRange
from .serializers import (
    CountrySerializer,
    MergeDuplicatesSerializer,
    ProductMergeSerializer,
    ProductRangeSerializer,
    ProductSerializer,
)
from .services import duplicate_groups, merge_duplicates, merge_products


class CountryViewSet(viewsets.ModelViewSet):
    """Countries are addressed by ISO2 code (`/countries/SN`) or by UUID."""

    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [IsAuthenticated, RolePermission]
    write_roles = GLOBAL_ROLES
    lookup_field = "iso2"
    lookup_value_regex = "[^/]+"
    search_fields = ["iso2", "name", "authority"]
    ordering_fields = ["iso2", "name"]

    def get_object(self):
        value = self.kwargs[self.lookup_field]
        queryset = self.filter_queryset(self.get_queryset())
        if len(value) == 2:
            obj = get_object_or_404(queryset, iso2=value.upper())
        else:
            obj = get_object_or_404(queryset, pk=value)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"], url_path="documents")
    def documents(self, request, iso2=None):
        from apps.documents.views import country_documents

        return country_documents(request, self.get_object())


class ProductRangeViewSet(viewsets.ModelViewSet):
    queryset = ProductRange.objects.all()
    serializer_class = ProductRangeSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    write_roles = GLOBAL_ROLES


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("range").prefetch_related("aliases")
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, RolePermission]
    write_roles = GLOBAL_ROLES
    action_roles = {"merge": CEO_ONLY, "duplicates": GLOBAL_ROLES, "merge_duplicates": CEO_ONLY}
    filterset_fields = {"range": ["exact"], "range__code": ["exact"], "is_active": ["exact"]}
    search_fields = ["name", "dci", "aliases__raw_name"]
    ordering_fields = ["name"]

    @extend_schema(request=ProductMergeSerializer, responses=ProductSerializer)
    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        keep = self.get_object()
        serializer = ProductMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duplicate = get_object_or_404(Product, pk=serializer.validated_data["duplicate_id"])
        if duplicate.pk == keep.pk:
            return Response(
                {"detail": "Le doublon doit être différent du produit conservé."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        merge_products(keep, duplicate)
        keep.refresh_from_db()
        return Response(self.get_serializer(keep).data)

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["get"], url_path="documents")
    def documents(self, request, pk=None):
        from apps.documents.views import product_documents

        return product_documents(request, self.get_object())

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def duplicates(self, request):
        """Groupes de produits en doublon probable (même clé de rapprochement)."""
        return Response(duplicate_groups())

    @extend_schema(request=MergeDuplicatesSerializer, responses={200: dict})
    @action(detail=False, methods=["post"], url_path="merge-duplicates")
    def merge_duplicates(self, request):
        """Fusionne tous les groupes sans conflit ; les groupes en conflit sont renvoyés."""
        serializer = MergeDuplicatesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(merge_duplicates(dry_run=serializer.validated_data["dry_run"]))
