"""Nightly recomputation of the denormalized AMM state."""

from datetime import date

from celery import shared_task

from apps.realtime.publisher import publish_dashboard_refresh

from .models import MarketingAuthorization
from .services.status import current_scans_prefetch, recompute_quietly


@shared_task(name="apps.amm.tasks.recompute_all_statuses")
def recompute_all_statuses(today: str | None = None) -> dict:
    reference = date.fromisoformat(today) if today else None
    changed = 0
    queryset = MarketingAuthorization.objects.select_related("country").prefetch_related(
        "renewals", current_scans_prefetch()
    )
    for amm in queryset.iterator(chunk_size=500):
        # Les prefetch de ce parcours sont à jour : on les passe pour éviter deux requêtes par AMM.
        if recompute_quietly(
            amm,
            today=reference,
            renewals=list(amm.renewals.all()),
            documents=list(amm.current_scans),
        ):
            changed += 1
    publish_dashboard_refresh()
    return {"changed": changed}
