"""Sentry : erreurs du web et du worker, actif seulement si `SENTRY_DSN` est défini.

Application réglementaire : aucune donnée personnelle n'est envoyée. `send_default_pii=False`
écarte adresse IP, cookies et identité ; le corps des requêtes n'est jamais joint (un upload de
scan ou une fiche d'AMM ne doit pas partir chez un tiers). Seul l'identifiant interne de
l'utilisateur est attaché, ce qui suffit à répondre à « combien d'utilisateurs touchés ? »
(docs/audit-resilience/RAPPORT.md) sans exposer qui que ce soit.

Les traces de performance sont désactivées par défaut (`SENTRY_TRACES_SAMPLE_RATE=0`) : les
latences viennent déjà des journaux JSON et de Prometheus.
"""

from __future__ import annotations

import logging
from typing import Any

# Interrogées en continu par les sondes et le navigateur : elles noieraient les traces.
QUIET_PATHS = ("/api/v1/health", "/metrics")

_initialised = False


def sentry_options(
    dsn: str | None,
    *,
    environment: str,
    release: str | None = None,
    traces_sample_rate: float = 0.0,
) -> dict[str, Any] | None:
    """Options passées à `sentry_sdk.init`, ou None quand aucun DSN n'est configuré."""
    if not dsn:
        return None
    return {
        "dsn": dsn,
        "environment": environment,
        "release": release or None,
        "traces_sample_rate": traces_sample_rate,
        "traces_sampler": _traces_sampler(traces_sample_rate),
        "send_default_pii": False,
        "max_request_body_size": "never",
    }


def _traces_sampler(default_rate: float):
    """Écarte les sondes de santé et les métriques, garde le taux demandé pour le reste."""

    def sampler(context: dict[str, Any]) -> float:
        scope = context.get("asgi_scope") or context.get("wsgi_environ") or {}
        path = scope.get("path") or scope.get("PATH_INFO") or ""
        return 0.0 if path.startswith(QUIET_PATHS) else default_rate

    return sampler


def init_sentry(
    dsn: str | None,
    *,
    environment: str,
    release: str | None = None,
    traces_sample_rate: float = 0.0,
) -> bool:
    """Initialise Sentry si un DSN est fourni. Retourne True quand la surveillance est active."""
    global _initialised
    options = sentry_options(
        dsn, environment=environment, release=release, traces_sample_rate=traces_sample_rate
    )
    if options is None:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        # Le paquet manque (image plus ancienne, installation partielle) : la surveillance passe
        # son tour. Elle ne doit jamais empêcher l'application de démarrer.
        logging.getLogger(__name__).warning(
            "SENTRY_DSN est défini mais sentry-sdk n'est pas installé : surveillance inactive."
        )
        return False

    sentry_sdk.init(
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            # Les journaux ERROR deviennent des événements ; le reste sert de fil d'Ariane.
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        **options,
    )
    _initialised = True
    return True


def is_active() -> bool:
    return _initialised


def bind_request(request_id: str | None = None, user_id: Any = None) -> None:
    """Relie l'événement Sentry à la requête : même identifiant que les journaux JSON."""
    if not _initialised:
        return
    import sentry_sdk

    if request_id:
        sentry_sdk.set_tag("request_id", request_id)
    # Identifiant interne seulement : ni e-mail, ni nom, ni adresse IP.
    sentry_sdk.set_user({"id": str(user_id)} if user_id else None)


def bind_task(task_name: str | None = None, request_id: str | None = None) -> None:
    """Même chose pour une tâche Celery, qui hérite de l'identifiant de la requête d'origine."""
    if not _initialised:
        return
    import sentry_sdk

    if request_id:
        sentry_sdk.set_tag("request_id", request_id)
    if task_name:
        sentry_sdk.set_tag("celery_task", task_name)
