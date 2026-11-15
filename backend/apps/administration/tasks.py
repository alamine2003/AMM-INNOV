"""Tâches d'administration : surveillance de la mémoire de Redis et des sauvegardes."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User
from apps.core.backups import backup_problems, copy_offsite
from apps.core.redis_usage import redis_memory
from apps.notifications.models import Notification
from apps.realtime.publisher import publish_user_event

logger = logging.getLogger(__name__)


def warn_ceos(subject: str, title: str, body: str) -> int:
    """Un avertissement dans l'application à chaque CEO, une fois par jour au plus par sujet
    (jamais d'e-mail). `subject` est le début du titre : il reconnaît l'avertissement déjà fait."""
    since = timezone.now() - timedelta(hours=24)
    notified = 0
    for user in User.objects.filter(is_active=True, role=User.Role.CEO_ADMIN):
        exists = Notification.objects.filter(
            user=user, title__startswith=subject, created_at__gte=since
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
    return notified


@shared_task(name="apps.administration.tasks.watch_redis_memory")
def watch_redis_memory() -> dict:
    """Redis presque plein : un avertissement dans l'application à chaque CEO, une fois par
    jour au plus (jamais d'e-mail)."""
    usage = redis_memory()
    if usage is None or usage["pct"] is None or usage["pct"] < settings.REDIS_WARN_PCT:
        return {"pct": usage and usage["pct"], "notified": 0}
    body = (
        f"La mémoire de Redis (file des tâches, cache, temps réel) est utilisée à "
        f"{usage['pct']:.0f} % ({usage['used'] // 1024} Ko sur {usage['limit'] // 1024} Ko). "
        "Plein, il refuse les nouvelles tâches : imports et rappels s'arrêteraient. "
        "Voir docs/audit-infrastructure-1.2.4.md (constat 9)."
    )
    notified = warn_ceos("Redis presque plein", f"Redis presque plein : {usage['pct']:.0f} %", body)
    return {"pct": usage["pct"], "notified": notified}


@shared_task(name="apps.administration.tasks.ship_backups")
def ship_backups() -> dict:
    """Chaque heure, sur un serveur : copie hors machine des sauvegardes vérifiées de la base,
    puis avertissement à chaque CEO si la sauvegarde échoue, ne tourne plus ou n'est plus
    copiée (une fois par jour au plus). Inactive sans BACKUP_DIR (Render)."""
    if not settings.BACKUP_DIR:
        return {"active": False}
    try:
        result = copy_offsite()
    except Exception as exc:
        # Avertissement seulement : le constat remonte par la notification et le contrôle
        # d'intégrité, sans une entrée au journal des erreurs chaque heure.
        logger.warning("Sauvegardes : copie hors du serveur impossible", exc_info=True)
        result = {"active": True, "copied": [], "removed": [], "error": str(exc)}
    if result["copied"] or result["removed"]:
        logger.info(
            "Sauvegardes : %s copiée(s) hors du serveur, %s ancienne(s) retirée(s)",
            len(result["copied"]),
            len(result["removed"]),
        )
    problems = backup_problems()
    notified = 0
    if problems:
        body = (
            " ".join(problems)
            + " Tant que ce n'est pas réglé, une panne du serveur ferait perdre les saisies "
            "depuis la dernière bonne sauvegarde. Voir docs/deploiement-serveur-partage.md "
            "(« Sauvegardes »)."
        )
        notified = warn_ceos("Sauvegarde de la base", "Sauvegarde de la base : à vérifier", body)
    return {**result, "problems": problems, "notified": notified}
