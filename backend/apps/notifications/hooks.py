"""Ce que l'app Notifications déclare au socle : rattrapage des e-mails et invariants."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from apps.core.integrity import ERROR, Check
from apps.core.registry import INTEGRITY, RECOVERY

# Au-delà (~5 h de panne Gmail couvertes, par exemple un quota d'envoi journalier dépassé), un
# e-mail est abandonné : l'échec reste visible (last_error, v_ops_backlog, check_integrity).
MAX_EMAIL_ATTEMPTS = 60
EMAIL_RETRY_AFTER = timedelta(minutes=15)  # laisse finir les relances Celery (≈ 10 min)


@RECOVERY.register
def recover_emails(now) -> dict[str, int]:
    """E-mails d'alerte jamais partis (Redis ou Gmail en panne) : renvoyés."""
    from .models import Notification
    from .tasks import send_alert_email

    emails = Notification.objects.filter(
        channel=Notification.Channel.EMAIL,
        sent_at__isnull=True,
        send_attempts__lt=MAX_EMAIL_ATTEMPTS,
        created_at__lt=now - EMAIL_RETRY_AFTER,
        created_at__gte=now - timedelta(days=2),
    ).exclude(last_attempt_at__gte=now - EMAIL_RETRY_AFTER)
    count = 0
    for pk in emails.values_list("pk", flat=True)[:500]:
        send_alert_email.delay(str(pk))
        count += 1
    return {"emails": count}


@INTEGRITY.register
def check_duplicate_notifications(options) -> Check:
    from .models import Notification

    check = Check(
        "no_duplicate_notification",
        ERROR,
        "Une alerte n'a-t-elle notifié chaque destinataire qu'une fois par canal ?",
    )
    rows = (
        Notification.objects.filter(alert__isnull=False)
        .values("alert_id", "user_id", "channel")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for row in rows:
        check.add(f"alerte {row['alert_id']} → {row['user_id']} ({row['channel']}) ×{row['n']}")
    return check


@INTEGRITY.register
def check_alerts_without_notification(options) -> Check:
    from apps.alerts.models import Alert

    from .services import recipients_for

    check = Check(
        "fresh_alert_notified",
        ERROR,
        "Une alerte récente (non silencieuse par conception) a-t-elle bien été notifiée ?",
    )
    max_age = settings.ALERTS_DISPATCH_MAX_AGE_DAYS
    candidates = (
        Alert.objects.filter(notifications__isnull=True)
        .select_related("rule", "amm__country")
        .exclude(rule__channels=[])
    )
    if options.since:
        candidates = candidates.filter(triggered_at__gte=options.since)
    for alert in candidates.iterator(chunk_size=500):
        fresh = (alert.triggered_at.date() - alert.due_date).days <= max_age
        if fresh and recipients_for(alert):
            check.add(f"alerte {alert.pk} ({alert.rule.code}, échéance {alert.due_date})")
    return check


@INTEGRITY.register
def check_unsent_emails(options) -> Check:
    from .models import Notification

    minutes = options.stuck_minutes
    check = Check(
        "email_delivered",
        ERROR,
        f"Un e-mail d'alerte reste-t-il non envoyé plus de {minutes} min après sa création ?",
    )
    limit = timezone.now() - timedelta(minutes=minutes)
    rows = Notification.objects.filter(
        channel=Notification.Channel.EMAIL, sent_at__isnull=True, created_at__lt=limit
    )
    if options.since:
        rows = rows.filter(created_at__gte=options.since)
    for pk in rows.values_list("pk", flat=True):
        check.add(f"notification {pk}")
    return check
