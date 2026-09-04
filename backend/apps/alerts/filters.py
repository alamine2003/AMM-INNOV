import django_filters

from .models import Alert


class AlertFilter(django_filters.FilterSet):
    status = django_filters.BaseInFilter(field_name="status", lookup_expr="in")
    country = django_filters.CharFilter(field_name="amm__country__iso2", lookup_expr="iexact")
    severity = django_filters.BaseInFilter(field_name="rule__severity", lookup_expr="in")
    code = django_filters.CharFilter(field_name="rule__code", lookup_expr="iexact")
    amm = django_filters.UUIDFilter(field_name="amm_id")
    assigned_to = django_filters.CharFilter(method="filter_assigned_to")
    due_before = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")

    class Meta:
        model = Alert
        fields = ["status", "country", "severity", "code", "amm", "assigned_to"]

    def filter_assigned_to(self, queryset, name, value):
        if value == "me":
            return queryset.filter(assigned_to=self.request.user)
        if value in {"none", "null", ""}:
            return queryset.filter(assigned_to__isnull=True)
        return queryset.filter(assigned_to_id=value)
