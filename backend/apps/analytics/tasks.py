"""Refresh of the PostgreSQL materialized views used by Grafana (no-op on other vendors)."""

import logging

from celery import shared_task
from django.db import connection

logger = logging.getLogger(__name__)

MATERIALIZED_VIEWS = ("analytics.mv_country_kpi", "analytics.mv_expiry_pipeline")


@shared_task(name="apps.analytics.tasks.refresh_analytics_views")
def refresh_analytics_views() -> dict:
    if connection.vendor != "postgresql":
        return {"refreshed": 0, "skipped": "not postgresql"}
    refreshed = 0
    with connection.cursor() as cursor:
        for view in MATERIALIZED_VIEWS:
            try:
                cursor.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                refreshed += 1
            except Exception as exc:  # pragma: no cover - view missing / concurrent refresh
                logger.warning("Rafraîchissement impossible de %s : %s", view, exc)
    return {"refreshed": refreshed}
