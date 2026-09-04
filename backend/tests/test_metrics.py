"""Custom Prometheus collector: works without Redis and reports AMM counts."""

from datetime import timedelta

import pytest
from prometheus_client import REGISTRY

from apps.core import metrics
from tests.conftest import TODAY


@pytest.mark.django_db
def test_amm_by_status_gauge(make_amm):
    make_amm()  # started one year ago: VALIDE
    make_amm(start=TODAY - timedelta(days=6 * 365))  # EXPIRE
    families = {f.name: f for f in metrics.AppCollector().collect()}
    gauge = families["amm_amm_by_status"]
    values = {s.labels["status"]: s.value for s in gauge.samples}
    assert values.get("VALIDE") == 1
    assert values.get("EXPIRE") == 1


def test_redis_helpers_are_best_effort(settings):
    settings.REDIS_URL = "redis://127.0.0.1:1/0"
    metrics.ws_connected()
    metrics.email_sent()
    metrics.celery_task_finished("x", "SUCCESS")
    assert metrics.AppCollector()._redis_metrics() is not None


def test_collector_registered_once():
    metrics.register_collector()
    metrics.register_collector()
    names = {c.__class__.__name__ for c in REGISTRY._collector_to_names}
    assert "AppCollector" in names
