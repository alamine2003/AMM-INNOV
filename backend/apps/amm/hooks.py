"""Ce que l'app AMM déclare au socle : invariants (check_integrity), métriques, et sa part
de la fusion de produits du catalogue."""

from __future__ import annotations

from collections import defaultdict

from django.db import connection
from django.db.models import Count

from apps.catalog.extensions import PRODUCT_COUNTRIES, PRODUCT_MERGE
from apps.core.integrity import ERROR, WARNING, Check
from apps.core.registry import INTEGRITY, METRICS

# Champs saisis par un utilisateur : l'historique doit toujours refléter la ligne courante.
# Les champs calculés (statut, urgence…) sont réécrits la nuit par update() sans historique.
AMM_TRACKED = (
    "original_number",
    "holder",
    "original_start_date",
    "original_end_date",
    "original_end_date_manual",
    "notes",
    "owner_id",
    "product_id",
    "country_id",
)
RENEWAL_TRACKED = (
    "workflow_status",
    "number",
    "filing_date",
    "decision_date",
    "start_date",
    "end_date",
    "notes",
)


@INTEGRITY.register
def check_amm_state(options) -> Check:
    from .models import MarketingAuthorization
    from .services.status import compute_amm_state, current_scans_prefetch

    check = Check(
        "amm_state_consistent",
        ERROR,
        "Le statut stocké de chaque AMM correspond-il à ses renouvellements et scans ?",
    )
    queryset = MarketingAuthorization.objects.select_related("country").prefetch_related(
        "renewals", current_scans_prefetch()
    )
    for amm in queryset.iterator(chunk_size=500):
        state = compute_amm_state(
            amm, renewals=list(amm.renewals.all()), documents=list(amm.current_scans)
        )
        if state.differs_from(amm):
            check.add(
                f"{amm.pk}: stocké {amm.status}/{amm.urgency}/{amm.effective_end_date}/"
                f"{amm.dossier_state} ≠ attendu {state.status}/{state.urgency}/"
                f"{state.effective_end_date}/{state.dossier_state}"
            )
    return check


@INTEGRITY.register
def check_single_open_renewal(options) -> Check:
    from .models import Renewal

    check = Check("single_open_renewal", ERROR, "Au plus un renouvellement ouvert par AMM ?")
    rows = (
        Renewal.objects.filter(workflow_status__in=Renewal.OPEN_STATUSES)
        .values("amm_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for row in rows:
        check.add(f"AMM {row['amm_id']}: {row['n']} renouvellements ouverts")
    return check


@INTEGRITY.register
def check_renewal_sequences(options) -> Check:
    from .models import Renewal

    check = Check(
        "renewal_sequence_contiguous",
        WARNING,
        "Les n° d'ordre des renouvellements forment-ils une suite 1..n ?",
    )
    by_amm = defaultdict(list)
    for amm_id, sequence in Renewal.objects.values_list("amm_id", "sequence"):
        by_amm[amm_id].append(sequence)
    for amm_id, sequences in by_amm.items():
        if sorted(sequences) != list(range(1, len(sequences) + 1)):
            check.add(f"AMM {amm_id}: {sorted(sequences)}")
    return check


def _latest_history(model, ids_field: str = "id"):
    """{object id: latest historical row} — DISTINCT ON sous PostgreSQL."""
    history = model.history.model.objects.all()
    if connection.vendor == "postgresql":
        rows = history.order_by(ids_field, "-history_date", "-history_id").distinct(ids_field)
        return {getattr(row, ids_field): row for row in rows}
    latest = {}
    for row in history.order_by("history_date", "history_id"):
        latest[getattr(row, ids_field)] = row
    return latest


@INTEGRITY.register
def check_history_matches_rows(options) -> Check:
    from .models import MarketingAuthorization, Renewal

    check = Check(
        "history_matches_rows",
        ERROR,
        "La dernière entrée d'historique reflète-t-elle la ligne (aucune écriture sans trace) ?",
    )
    for model, fields, label in (
        (MarketingAuthorization, AMM_TRACKED, "AMM"),
        (Renewal, RENEWAL_TRACKED, "Renouvellement"),
    ):
        latest = _latest_history(model)
        for obj in model.objects.all().iterator(chunk_size=1000):
            row = latest.get(obj.pk)
            if row is None:
                check.add(f"{label} {obj.pk}: aucune entrée d'historique")
                continue
            diff = [f for f in fields if getattr(obj, f) != getattr(row, f)]
            if diff:
                check.add(f"{label} {obj.pk}: {', '.join(diff)} modifiés sans historique")
    return check


@METRICS.register
def amm_by_status():
    from prometheus_client.core import GaugeMetricFamily

    from .models import MarketingAuthorization

    gauge = GaugeMetricFamily(
        "amm_amm_by_status", "Nombre d'AMM par statut calculé", labels=["status"]
    )
    try:
        rows = MarketingAuthorization.objects.values("status").annotate(n=Count("id"))
        for row in rows:
            gauge.add_metric([row["status"]], row["n"])
    except Exception:  # base indisponible pendant la collecte
        return
    yield gauge


# --- Catalogue : fusion de produits ---------------------------------------------------------


@PRODUCT_MERGE.register
def merge_product_amms(keep, duplicate) -> None:
    """Les AMM du doublon passent au produit gardé. Si les deux avaient une AMM dans le même
    pays, l'AMM gardée reprend renouvellements, documents et alertes : l'historique reste."""
    from .models import MarketingAuthorization

    for amm in MarketingAuthorization.objects.filter(product=duplicate):
        existing = MarketingAuthorization.objects.filter(product=keep, country=amm.country).first()
        if existing is None:
            amm.product = keep
            amm.save()
        else:
            amm.renewals.update(amm=existing)
            amm.documents.update(amm=existing)
            amm.alerts.update(amm=existing)
            amm.delete()
            existing.save()


@PRODUCT_COUNTRIES.register
def product_countries(products) -> dict:
    from .models import MarketingAuthorization

    countries: dict = defaultdict(list)
    rows = MarketingAuthorization.objects.filter(product__in=products).values_list(
        "product_id", "country__iso2"
    )
    for product_id, iso2 in rows:
        countries[product_id].append(iso2)
    return dict(countries)
