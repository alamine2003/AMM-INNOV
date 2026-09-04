"""Application metrics exposed on /metrics (django-prometheus).

Counters produced by other processes (Celery worker, Daphne) are kept in Redis so that
the web process can expose them; every write is best-effort and silently skipped when
Redis is unavailable (tests, local runs without Redis).
"""

from __future__ import annotations

import logging

from django.conf import settings
from prometheus_client import REGISTRY
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

logger = logging.getLogger(__name__)

KEY_WS = "metrics:ws_connections"
KEY_EMAILS_SENT = "metrics:emails_sent_total"
KEY_EMAILS_FAILED = "metrics:emails_failed_total"
KEY_CELERY_TASKS = "metrics:celery_tasks_total"  # hash "<name>|<state>" -> count
CELERY_QUEUES = ("celery",)


def _client():
    try:
        import redis

        return redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.5)
    except Exception:  # pragma: no cover - import or URL errors
        return None


def _safe(fn):
    client = _client()
    if client is None:
        return None
    try:
        return fn(client)
    except Exception:
        return None


def ws_connected() -> None:
    _safe(lambda c: c.incr(KEY_WS))


def ws_disconnected() -> None:
    _safe(lambda c: c.decr(KEY_WS))


def email_sent() -> None:
    _safe(lambda c: c.incr(KEY_EMAILS_SENT))


def email_failed() -> None:
    _safe(lambda c: c.incr(KEY_EMAILS_FAILED))


def celery_task_finished(name: str, state: str) -> None:
    _safe(lambda c: c.hincrby(KEY_CELERY_TASKS, f"{name}|{state}", 1))


class AppCollector:
    """Custom Prometheus collector computed at scrape time."""

    def describe(self):
        """Declare metric names without touching the database at registration time."""
        yield GaugeMetricFamily(
            "amm_amm_by_status", "Nombre d'AMM par statut calculé", labels=["status"]
        )
        yield GaugeMetricFamily("amm_websocket_connections", "Connexions WebSocket ouvertes")
        yield CounterMetricFamily("amm_emails_sent", "Emails d'alerte envoyés")
        yield CounterMetricFamily("amm_emails_failed", "Emails d'alerte en échec")
        yield CounterMetricFamily(
            "celery_tasks", "Tâches Celery terminées", labels=["name", "state"]
        )
        yield GaugeMetricFamily(
            "celery_queue_length", "Messages en attente dans la file", labels=["queue"]
        )

    def collect(self):
        yield from self._amm_by_status()
        yield from self._redis_metrics()

    def _amm_by_status(self):
        gauge = GaugeMetricFamily(
            "amm_amm_by_status", "Nombre d'AMM par statut calculé", labels=["status"]
        )
        try:
            from django.db.models import Count

            from apps.amm.models import MarketingAuthorization

            rows = MarketingAuthorization.objects.values("status").annotate(n=Count("id"))
            for row in rows:
                gauge.add_metric([row["status"]], row["n"])
        except Exception:  # database unavailable during scrape
            return
        yield gauge

    def _redis_metrics(self):
        client = _client()
        if client is None:
            return
        try:
            ws = GaugeMetricFamily("amm_websocket_connections", "Connexions WebSocket ouvertes")
            ws.add_metric([], max(int(client.get(KEY_WS) or 0), 0))
            yield ws

            sent = CounterMetricFamily("amm_emails_sent", "Emails d'alerte envoyés")
            sent.add_metric([], int(client.get(KEY_EMAILS_SENT) or 0))
            yield sent

            failed = CounterMetricFamily("amm_emails_failed", "Emails d'alerte en échec")
            failed.add_metric([], int(client.get(KEY_EMAILS_FAILED) or 0))
            yield failed

            tasks = CounterMetricFamily(
                "celery_tasks", "Tâches Celery terminées", labels=["name", "state"]
            )
            for key, value in client.hgetall(KEY_CELERY_TASKS).items():
                name, _, state = key.decode().partition("|")
                tasks.add_metric([name, state], int(value))
            yield tasks

            queue = GaugeMetricFamily(
                "celery_queue_length", "Messages en attente dans la file", labels=["queue"]
            )
            for name in CELERY_QUEUES:
                queue.add_metric([name], client.llen(name))
            yield queue
        except Exception:
            return


_registered = False


def register_collector() -> None:
    global _registered
    if _registered:
        return
    try:
        REGISTRY.register(AppCollector())
        _registered = True
    except ValueError:  # already registered (autoreload)
        _registered = True
