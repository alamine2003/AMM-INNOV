from datetime import date

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ensure_country_in_scope
from apps.amm.views import AmmViewSet
from apps.catalog.models import Country, Product

from .exports import build_csv, build_xlsx
from .services import africa_table, country_dashboard, product_coverage

TODAY_PARAM = OpenApiParameter(
    "today", str, description="Date de référence AAAA-MM-JJ (par défaut : aujourd'hui)."
)


def _today(request) -> date | None:
    raw = request.query_params.get("today")
    return date.fromisoformat(raw) if raw else None


class AfricaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[TODAY_PARAM], responses={200: dict})
    def get(self, request):
        return Response(africa_table(request.user, _today(request)))


class CountryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[TODAY_PARAM], responses={200: dict})
    def get(self, request, iso2: str):
        country = get_object_or_404(Country, iso2=iso2.upper())
        ensure_country_in_scope(request.user, country)
        return Response(country_dashboard(country, _today(request)))


class ProductCoverageView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: dict})
    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        return Response(product_coverage(product, request.user))


class ExportView(APIView):
    """`?format=xlsx|csv` with the same filters as `/amms` (`country`, `status`, `search`…)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[OpenApiParameter("format", str, description="xlsx (défaut) ou csv")],
        responses={(200, "application/octet-stream"): bytes},
    )
    def get(self, request):
        # Réutilise le viewset des AMM : périmètre pays, filtres, recherche et tri identiques
        # à la grille, pour que l'export corresponde exactement à la vue filtrée.
        view = AmmViewSet(request=request, action="list", kwargs={}, format_kwarg=None)
        queryset = view.filter_queryset(view.get_queryset())
        if not request.query_params.get("ordering"):
            queryset = queryset.order_by("country__name", "product__name")
        export_format = request.query_params.get("format", "xlsx").lower()
        stamp = date.today().strftime("%Y%m%d")
        if export_format == "csv":
            response = HttpResponse(build_csv(queryset), content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="amm_export_{stamp}.csv"'
            return response
        response = HttpResponse(
            build_xlsx(queryset),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="amm_export_{stamp}.xlsx"'
        return response
