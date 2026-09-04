"""Dashboard aggregates computed with the ORM (portable: SQLite in tests, PostgreSQL in prod)."""

from datetime import date

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Q

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country
from apps.core.dates import today as reference_today

S = MarketingAuthorization.Status
KPI_KEYS = (
    "total",
    "valid",
    "expired",
    "in_process",
    "undetermined",
    "expiring_6m",
    "expiring_12m",
    "complete",
)


def scoped_amms(user):
    queryset = MarketingAuthorization.objects.all()
    if user is not None and not user.is_global:
        queryset = queryset.filter(country__in=user.countries.all())
    return queryset


def scoped_countries(user):
    queryset = Country.objects.all()
    if user is not None and not user.is_global:
        queryset = user.countries.all()
    return queryset.order_by("name")


def _pct(part: int, total: int) -> float:
    return round(100.0 * part / total, 1) if total else 0.0


def _kpi_annotations(today: date) -> dict:
    return {
        "total": Count("id"),
        "valid": Count("id", filter=Q(status=S.VALIDE)),
        "expired": Count("id", filter=Q(status=S.EXPIRE)),
        "in_process": Count("id", filter=Q(status=S.IN_PROCESS)),
        "undetermined": Count("id", filter=Q(status=S.INDETERMINE)),
        "expiring_6m": Count(
            "id",
            filter=Q(status=S.VALIDE, effective_end_date__lte=today + relativedelta(months=6)),
        ),
        "expiring_12m": Count(
            "id",
            filter=Q(status=S.VALIDE, effective_end_date__lte=today + relativedelta(months=12)),
        ),
        "complete": Count(
            "id", filter=Q(dossier_state=MarketingAuthorization.DossierState.COMPLET)
        ),
    }


def _row(iso2: str, name: str, values: dict) -> dict:
    total = values.get("total", 0)
    row = {"country_iso2": iso2, "country_name": name}
    for key in KPI_KEYS:
        row[key] = values.get(key, 0)
    row["pct_valid"] = _pct(row["valid"], total)
    row["pct_complete"] = _pct(row["complete"], total)
    return row


def africa_table(user=None, today: date | None = None) -> dict:
    """Equivalent of the DASHBOARD sheet: one row per country plus a TOTAL row."""
    today = today or reference_today()
    aggregates = {
        item["country__iso2"]: item
        for item in scoped_amms(user)
        .values("country__iso2", "country__name")
        .annotate(**_kpi_annotations(today))
    }
    rows = [
        _row(country.iso2, country.name, aggregates.get(country.iso2, {}))
        for country in scoped_countries(user)
    ]
    totals = {key: sum(row[key] for row in rows) for key in KPI_KEYS}
    total_row = _row("ALL", "TOTAL", totals)
    return {"rows": rows, "total": total_row, "today": today}


def country_dashboard(country: Country, today: date | None = None) -> dict:
    today = today or reference_today()
    amms = MarketingAuthorization.objects.filter(country=country)
    by_range_status = [
        {
            "range": item["product__range__code"] or "SANS_GAMME",
            "status": item["status"],
            "count": item["count"],
        }
        for item in amms.values("product__range__code", "status")
        .annotate(count=Count("id"))
        .order_by("product__range__code", "status")
    ]
    start = today.replace(day=1)
    months = [start + relativedelta(months=i) for i in range(24)]
    end_limit = start + relativedelta(months=24)
    counts: dict[str, int] = {}
    for value in amms.filter(
        effective_end_date__gte=start, effective_end_date__lt=end_limit
    ).values_list("effective_end_date", flat=True):
        key = value.strftime("%Y-%m")
        counts[key] = counts.get(key, 0) + 1
    pipeline = [
        {"month": m.strftime("%Y-%m"), "count": counts.get(m.strftime("%Y-%m"), 0)} for m in months
    ]
    priorities = [
        {
            "id": str(amm.id),
            "product_name": amm.product.name,
            "range_code": amm.product.range.code if amm.product.range_id else None,
            "original_number": amm.original_number,
            "status": amm.status,
            "urgency": amm.urgency,
            "effective_end_date": amm.effective_end_date,
            "filing_deadline": amm.filing_deadline,
            "dossier_state": amm.dossier_state,
            "days_remaining": (amm.effective_end_date - today).days
            if amm.effective_end_date
            else None,
        }
        for amm in amms.exclude(status=S.INDETERMINE)
        .exclude(effective_end_date__isnull=True)
        .select_related("product", "product__range")
        .order_by("effective_end_date", "product__name")[:20]
    ]
    kpi = africa_table(None, today)
    country_row = next((r for r in kpi["rows"] if r["country_iso2"] == country.iso2), None)
    return {
        "country": {"iso2": country.iso2, "name": country.name},
        "kpi": country_row,
        "by_range_status": by_range_status,
        "pipeline": pipeline,
        "priorities": priorities,
        "today": today,
    }


def product_coverage(product, user=None) -> list[dict]:
    """One entry per country: the AMM status there, or null when the product is absent."""
    amms = {
        amm.country_id: amm
        for amm in MarketingAuthorization.objects.filter(product=product).select_related("country")
    }
    rows = []
    for country in Country.objects.order_by("name"):
        amm = amms.get(country.pk)
        rows.append(
            {
                "country_iso2": country.iso2,
                "country_name": country.name,
                "amm_id": str(amm.id) if amm else None,
                "status": amm.status if amm else None,
                "urgency": amm.urgency if amm else None,
                "effective_end_date": amm.effective_end_date if amm else None,
                "in_scope": user is None or user.is_global or user.can_access_country(country),
            }
        )
    return rows


EXPORT_COLUMNS = [
    "PAYS",
    "GAMME",
    "NOM",
    "DATE DEBUT",
    "N° AMM",
    "DATE FIN",
    "RENOUV. DATE DEBUT",
    "RENOUV. N° AMM",
    "RENOUV. DATE FIN",
    "STATUT",
    "ETAT DOSSIER",
    "URGENCE",
    "DEADLINE DEPOT",
]


def export_rows(queryset) -> list[list]:
    """Rows in the workbook column layout (last renewal = highest sequence)."""
    rows = []
    for amm in queryset.select_related("country", "product", "product__range").prefetch_related(
        "renewals"
    ):
        renewals = list(amm.renewals.all())
        last = max(renewals, key=lambda r: r.sequence) if renewals else None
        if last is not None and last.workflow_status in Renewal.PENDING_STATUSES:
            renewal_start = "IN PROCESS"
        else:
            renewal_start = last.start_date if last else None
        rows.append(
            [
                amm.country.name,
                amm.product.range.label if amm.product.range_id else "",
                amm.product.name,
                amm.original_start_date,
                amm.original_number,
                amm.original_end_date,
                renewal_start,
                last.number if last else "",
                last.end_date if last else None,
                amm.status,
                amm.get_dossier_state_display(),
                amm.urgency,
                amm.filing_deadline,
            ]
        )
    return rows
