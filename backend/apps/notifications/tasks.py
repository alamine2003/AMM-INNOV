"""Email delivery (with retries), weekly digest, cleanup."""

import logging
from datetime import timedelta
from email.utils import parseaddr

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import User
from apps.alerts.models import Alert
from apps.amm.models import MarketingAuthorization, Renewal
from apps.core import metrics
from apps.core.dates import today as reference_today

from .models import Notification

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.notifications.tasks.send_alert_email",
    bind=True,
    autoretry_for=(Exception,),
    # 30 s, 1, 2, 4, 8 min (≈ 15 min) : l'ancienne politique (1, 2, 4 s) abandonnait l'e-mail
    # après 7 s d'erreurs Gmail (s13). Au-delà, recover_pending_work reprend toutes les 15 min.
    # Plafond sous le visibility_timeout Redis (1 h), sinon la relance serait redistribuée.
    retry_backoff=30,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def send_alert_email(self, notification_id: str) -> dict:
    try:
        notification = Notification.objects.select_related("user", "alert").get(pk=notification_id)
    except Notification.DoesNotExist:
        return {"status": "missing"}
    if notification.sent_at is not None:
        return {"status": "already-sent"}
    message = render_to_string(
        "notifications/alert_email.txt",
        {
            "notification": notification,
            "user": notification.user,
            "frontend_url": settings.FRONTEND_URL,
        },
    )
    Notification.objects.filter(pk=notification.pk).update(
        send_attempts=F("send_attempts") + 1, last_attempt_at=timezone.now()
    )
    try:
        send_alert_message(notification, message)
    except Exception as exc:
        metrics.email_failed()
        Notification.objects.filter(pk=notification.pk).update(
            last_error=f"{type(exc).__name__}: {exc}"[:500]
        )
        raise
    metrics.email_sent()
    Notification.objects.filter(pk=notification.pk).update(sent_at=timezone.now(), last_error="")
    return {"status": "sent"}


def send_alert_message(notification: Notification, body: str) -> None:
    """Un Message-ID stable par notification : si Google a envoyé le message mais que sa réponse
    s'est perdue, la relance repart avec le même identifiant, que Gmail et la plupart des
    messageries fusionnent au lieu d'afficher un doublon (s13 « ack_lost » : 4 envois par
    e-mail). Mieux vaut un doublon fusionné qu'une alerte réglementaire perdue."""
    domain = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2] or "amm-innov.local"
    EmailMessage(
        subject=notification.title,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[notification.user.email],
        headers={"Message-ID": f"<notification-{notification.pk}@{domain}>"},
    ).send()


def digest_for_user(user: User, today=None) -> dict | None:
    """Open alerts, AMM to file within 6 months, incomplete dossiers, for the user's scope."""
    today = today or reference_today()
    amms = MarketingAuthorization.objects.select_related("country", "product")
    alerts = Alert.objects.filter(status__in=Alert.OPEN_STATUSES).select_related(
        "rule", "amm__country", "amm__product"
    )
    if not user.is_global:
        countries = user.countries.all()
        amms = amms.filter(country__in=countries)
        alerts = alerts.filter(amm__country__in=countries)
    pending_ids = Renewal.objects.filter(workflow_status__in=Renewal.PENDING_STATUSES).values(
        "amm_id"
    )
    to_file = amms.filter(status=MarketingAuthorization.Status.A_RENOUVELER).exclude(
        pk__in=pending_ids
    )
    incomplete = amms.filter(dossier_state=MarketingAuthorization.DossierState.INCOMPLET).exclude(
        status=MarketingAuthorization.Status.EXPIRE
    )
    payload = {
        "alerts": list(alerts.order_by("due_date")[:100]),
        "to_file": list(to_file.order_by("effective_end_date")[:100]),
        "incomplete": list(incomplete.order_by("effective_end_date")[:100]),
    }
    if not any(payload.values()):
        return None
    return payload


@shared_task(name="apps.notifications.tasks.send_weekly_digest")
def send_weekly_digest(today: str | None = None) -> dict:
    from datetime import date

    reference = date.fromisoformat(today) if today else reference_today()
    title = f"Digest hebdomadaire du {reference:%d/%m/%Y}"
    already = set(
        Notification.objects.filter(
            channel=Notification.Channel.EMAIL, title=title, sent_at__isnull=False
        ).values_list("user_id", flat=True)
    )
    sent = failed = 0
    for user in User.objects.filter(is_active=True).prefetch_related("countries"):
        # Relancé après un échec partiel, le digest ne repart qu'aux utilisateurs non servis.
        if user.pk in already:
            continue
        digest = digest_for_user(user, today=reference)
        if digest is None:
            continue
        message = render_to_string(
            "notifications/weekly_digest.txt",
            {"user": user, "today": reference, "frontend_url": settings.FRONTEND_URL, **digest},
        )
        try:
            send_mail(
                subject=f"AMM GH — {title}",
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
        except Exception:
            # Un destinataire en échec n'arrête plus la tournée des suivants.
            failed += 1
            metrics.email_failed()
            logger.exception("Digest non envoyé à %s", user.email)
            continue
        Notification.objects.create(
            user=user,
            channel=Notification.Channel.EMAIL,
            title=title,
            body=message,
            link=f"{settings.FRONTEND_URL.rstrip('/')}/alerts",
            sent_at=timezone.now(),
        )
        sent += 1
    return {"sent": sent, "failed": failed}


@shared_task(name="apps.notifications.tasks.send_renewal_reminders")
def send_renewal_reminders(today: str | None = None) -> dict:
    """Rappel quotidien des AMM « À renouveler » (idempotent sur la journée)."""
    from datetime import date

    from .reminders import send_renewal_reminders as run

    return run(today=date.fromisoformat(today) if today else None)


@shared_task(name="apps.notifications.tasks.cleanup_notifications")
def cleanup_notifications(days: int = 90) -> dict:
    limit = timezone.now() - timedelta(days=days)
    deleted, _ = Notification.objects.filter(read_at__lt=limit).delete()
    return {"deleted": deleted}
