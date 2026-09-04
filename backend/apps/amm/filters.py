import django_filters
from django.db.models import Q

from .models import MarketingAuthorization, Renewal


class AmmFilter(django_filters.FilterSet):
    country = django_filters.CharFilter(method="filter_country")
    range = django_filters.CharFilter(method="filter_range")
    status = django_filters.BaseInFilter(field_name="status", lookup_expr="in")
    urgency = django_filters.BaseInFilter(field_name="urgency", lookup_expr="in")
    dossier_state = django_filters.BaseInFilter(field_name="dossier_state", lookup_expr="in")
    expires_before = django_filters.DateFilter(field_name="effective_end_date", lookup_expr="lte")
    expires_after = django_filters.DateFilter(field_name="effective_end_date", lookup_expr="gte")
    product = django_filters.UUIDFilter(field_name="product_id")
    owner = django_filters.UUIDFilter(field_name="owner_id")
    has_current_scan = django_filters.BooleanFilter(field_name="has_current_scan")

    class Meta:
        model = MarketingAuthorization
        fields = ["country", "range", "status", "urgency", "dossier_state", "product", "owner"]

    def filter_country(self, queryset, name, value):
        values = [v.strip() for v in value.split(",") if v.strip()]
        query = Q()
        for v in values:
            if len(v) == 2:
                query |= Q(country__iso2=v.upper())
            else:
                query |= Q(country_id=v)
        return queryset.filter(query) if values else queryset

    def filter_range(self, queryset, name, value):
        values = [v.strip().upper() for v in value.split(",") if v.strip()]
        query = Q()
        for v in values:
            if len(v) > 16:
                query |= Q(product__range_id=v)
            else:
                query |= Q(product__range__code=v)
        return queryset.filter(query) if values else queryset


class RenewalFilter(django_filters.FilterSet):
    amm = django_filters.UUIDFilter(field_name="amm_id")
    country = django_filters.CharFilter(field_name="amm__country__iso2", lookup_expr="iexact")
    workflow_status = django_filters.BaseInFilter(field_name="workflow_status", lookup_expr="in")

    class Meta:
        model = Renewal
        fields = ["amm", "country", "workflow_status"]
