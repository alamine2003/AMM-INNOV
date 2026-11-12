"""Tâches d'administration : surveillance de la mémoire de Redis."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User
from apps.core.redis_usage import redis_memory
from apps.notifications.models import Notification
from apps.realtime.publisher import publish_user_event


@shared_task(name="apps.administration.tasks.watch_redis_memory")
def watch_redis_memory() -> dict:
    """Redis presque plein : un avertissement dans l'application à chaque CEO, une fois par
    jour au plus (jamais d'e-mail)."""
    usage = redis_memory()
    if usage is None or usage["pct"] is None or usage["pct"] < settings.REDIS_WARN_PCT:
        return {"pct": usage and usage["pct"], "notified": 0}
    title = f"Redis presque plein : {usage['pct']:.0f} %"
    body = (
        f"La mémoire de Redis (file des tâches, cache, temps réel) est utilisée à "
        f"{usage['pct']:.0f} % ({usage['used'] // 1024} Ko sur {usage['limit'] // 1024} Ko). "
        "Plein, il refuse les nouvelles tâches : imports et rappels s'arrêteraient. "
        "Voir docs/audit-infrastructure-1.2.4.md (constat 9)."
    )
    since = timezone.now() - timedelta(hours=24)
    notified = 0
    for user in User.objects.filter(is_active=True, role=User.Role.CEO_ADMIN):
        exists = Notification.objects.filter(
            user=user, title__startswith="Redis presque plein", created_at__gte=since
        ).exists()
        if exists:
            continue
        notification = Notification.objects.create(
            user=user,
            channel=Notification.Channel.IN_APP,
            title=title,
            body=body,
            link=f"{settings.FRONTEND_URL.rstrip('/')}/admin/erreurs",
            sent_at=timezone.now(),
        )
        publish_user_event(user.pk, "notification.created", notification.pk)
        notified += 1
    return {"pct": usage["pct"], "notified": notified}
