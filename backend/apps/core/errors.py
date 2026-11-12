"""Journal des erreurs de production, sans service externe (version 1.2.5).

Trois portes d'entrée :

- une requête qui lève une exception (signal `got_request_exception` de Django) ;
- une tâche Celery en échec (signal `task_failure`) ;
- l'interface, qui envoie ses propres erreurs (`POST /api/v1/client-errors`).

Une erreur est regroupée par empreinte (origine, type, message sans chiffres, lieu) : sa
répétition incrémente le compteur. Une erreur résolue qui revient est rouverte. Enregistrer ne
doit jamais provoquer une seconde panne : toute défaillance ici est avalée et journalisée.
"""

from __future__ import annotations

import hashlib
import logging
import re
import traceback

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_DETAIL = 8000
_NUMBERS = re.compile(r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b|\d+")


def fingerprint(source: str, kind: str, message: str, location: str) -> str:
    """Même erreur = même empreinte, quels que soient les identifiants dans le message."""
    stable = _NUMBERS.sub("#", message)[:300]
    return hashlib.sha256(f"{source}|{kind}|{stable}|{location}".encode()).hexdigest()


def record(
    *,
    source: str,
    kind: str,
    message: str,
    detail: str = "",
    location: str = "",
    user=None,
    version: str = "",
):
    """Enregistre (ou recompte) une erreur. Ne lève jamais."""
    try:
        from .models import ErrorEvent

        now = timezone.now()
        key = fingerprint(source, kind, message, location)
        user_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
        with transaction.atomic():
            updated = ErrorEvent.objects.filter(fingerprint=key).update(
                count=F("count") + 1,
                last_seen=now,
                last_user_id=user_id,
                detail=detail[:MAX_DETAIL],
                version=(version or settings.APP_VERSION)[:20],
                resolved_at=None,
                resolved_by=None,
            )
            if not updated:
                ErrorEvent.objects.create(
                    fingerprint=key,
                    source=source,
                    kind=kind[:120],
                    message=(message or kind)[:500],
                    detail=detail[:MAX_DETAIL],
                    location=location[:300],
                    version=(version or settings.APP_VERSION)[:20],
                    last_seen=now,
                    last_user_id=user_id,
                )
    except Exception:  # base indisponible, transaction cassée… : jamais de seconde panne
        logger.warning("Journal des erreurs : enregistrement impossible", exc_info=True)


def _trace(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-MAX_DETAIL:]


def on_request_exception(sender, request=None, **kwargs):
    import sys

    exc = sys.exc_info()[1]
    if exc is None:
        return
    # 4xx « attendues » (Http404, PermissionDenied…) ne sont pas des pannes.
    from django.core.exceptions import PermissionDenied, SuspiciousOperation
    from django.http import Http404

    if isinstance(exc, Http404 | PermissionDenied | SuspiciousOperation):
        return
    location = ""
    if request is not None:
        match = getattr(request, "resolver_match", None)
        location = f"{request.method} {match.route if match else request.path}"
    record(
        source="server",
        kind=type(exc).__name__,
        message=str(exc),
        detail=_trace(exc),
        location=location,
        user=getattr(request, "user", None),
    )


def on_task_failure(sender=None, exception=None, einfo=None, **kwargs):
    if exception is None:
        return
    record(
        source="worker",
        kind=type(exception).__name__,
        message=str(exception),
        detail=str(einfo or "")[-MAX_DETAIL:],
        location=getattr(sender, "name", "") or "",
    )


def connect() -> None:
    from celery.signals import task_failure
    from django.core.signals import got_request_exception

    got_request_exception.connect(on_request_exception, dispatch_uid="amm-error-journal")
    task_failure.connect(on_task_failure, dispatch_uid="amm-error-journal-task", weak=False)
