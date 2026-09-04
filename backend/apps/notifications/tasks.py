"""Email delivery (with retries), weekly digest, cleanup."""

import logging
from datetime import timedelta

from celery import shared_task
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import send_mail
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
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
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
    try:
        send_mail(
            subject=notification.title,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.user.email],
        )
    except Exception:
        metrics.email_failed()
        raise
    metrics.email_sent()
    Notification.objects.filter(pk=notification.pk).update(sent_at=timezone.now())
    return {"status": "sent"}


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
    to_file = amms.filter(
        status=MarketingAuthorization.Status.VALIDE,
        effective_end_date__lte=today + relativedelta(months=6),
    ).exclude(pk__in=pending_ids)
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
    sent = 0
    for user in User.objects.filter(is_active=True).prefetch_related("countries"):
        digest = digest_for_user(user, today=reference)
        if digest is None:
            continue
        message = render_to_string(
            "notifications/weekly_digest.txt",
            {"user": user, "today": reference, "frontend_url": settings.FRONTEND_URL, **digest},
        )
        send_mail(
            subject=f"AMM INNOV — Digest hebdomadaire du {reference:%d/%m/%Y}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        Notification.objects.create(
            user=user,
            channel=Notification.Channel.EMAIL,
            title=f"Digest hebdomadaire du {reference:%d/%m/%Y}",
            body=message,
            link=f"{settings.FRONTEND_URL.rstrip('/')}/alerts",
            sent_at=timezone.now(),
        )
        sent += 1
    return {"sent": sent}


@shared_task(name="apps.notifications.tasks.cleanup_notifications")
def cleanup_notifications(days: int = 90) -> dict:
    limit = timezone.now() - timedelta(days=days)
    deleted, _ = Notification.objects.filter(read_at__lt=limit).delete()
    return {"deleted": deleted}
