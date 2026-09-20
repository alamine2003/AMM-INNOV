"""Journaux structurés et identifiant de requête (campagne de chaos, phase 4).

Pendant les pannes du laboratoire, les journaux ne permettaient pas de répondre « quelle
requête, quel utilisateur, combien de temps, quelle tâche en découle ? » : lignes texte sans
identifiant, pas de journal d'accès sous uvicorn (--no-access-log), rien pour relier un e-mail en
échec à la requête qui l'avait déclenché.

- chaque requête porte un identifiant (X-Request-ID posé par nginx, sinon généré), renvoyé au
  client et présent sur chaque ligne de journal ;
- une ligne d'accès JSON par requête : méthode, chemin, statut, durée, utilisateur ;
- l'identifiant suit les tâches Celery publiées par la requête (en-tête `request_id`).
"""

from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid

from config import sentry

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

access_logger = logging.getLogger("amm.access")
QUIET_PATHS = ("/api/v1/health", "/metrics")
EXTRA_FIELDS = ("method", "path", "status", "duration_ms", "user_id", "task", "task_id")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    """Une ligne JSON par événement : lisible par Railway, Loki ou n'importe quel grep."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key in EXTRA_FIELDS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = (request.headers.get("X-Request-ID") or uuid.uuid4().hex)[:64]
        token = request_id_var.set(request_id)
        started = time.monotonic()
        sentry.bind_request(request_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            if not request.path.startswith(QUIET_PATHS):
                user = getattr(request, "user", None)
                access_logger.info(
                    "%s %s %s",
                    request.method,
                    request.path,
                    response.status_code,
                    extra={
                        "method": request.method,
                        "path": request.path,
                        "status": response.status_code,
                        "duration_ms": round((time.monotonic() - started) * 1000, 1),
                        "user_id": getattr(user, "pk", None),
                    },
                )
            # L'utilisateur n'est connu qu'après l'authentification, donc après la vue.
            sentry.bind_request(user_id=getattr(getattr(request, "user", None), "pk", None))
            return response
        finally:
            request_id_var.reset(token)


# --- Celery : l'identifiant de la requête suit la tâche -------------------------------------


def attach_request_id(headers=None, **kwargs) -> None:
    if headers is not None and request_id_var.get() != "-":
        headers.setdefault("request_id", request_id_var.get())


def bind_task_context(task=None, task_id=None, **kwargs) -> None:
    parent = getattr(task.request, "request_id", None) if task is not None else None
    request_id_var.set(parent or f"task-{task_id}")
    sentry.bind_task(getattr(task, "name", None), parent)
