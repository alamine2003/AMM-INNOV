"""Fan-out of an alert to its recipients on each channel of the rule."""

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User
from apps.alerts.models import Alert
from apps.core.tasks import enqueue
from apps.realtime.publisher import publish_user_event

from .models import Notification

SEVERITY_LABEL = {"INFO": "Info", "WARNING": "Attention", "CRITICAL": "Critique"}


def recipients_for(alert: Alert):
    roles = alert.rule.roles or []
    users = User.objects.filter(is_active=True, role__in=roles)
    country_id = alert.amm.country_id
    return [
        u
        for u in users.prefetch_related("countries")
        if u.is_global or u.countries.filter(pk=country_id).exists()
    ]


def alert_title(alert: Alert) -> str:
    amm = alert.amm
    label = SEVERITY_LABEL.get(alert.rule.severity, alert.rule.severity)
    return f"[{label}] {alert.rule.code} — {amm.product.name} ({amm.country.iso2})"


def alert_body(alert: Alert) -> str:
    amm = alert.amm
    end = amm.effective_end_date.strftime("%d/%m/%Y") if amm.effective_end_date else "inconnue"
    deadline = amm.filing_deadline.strftime("%d/%m/%Y") if amm.filing_deadline else "inconnue"
    where = f"{amm.product.name} au {amm.country.name}"
    if alert.rule.code == "J0":
        return f"L'AMM {amm.original_number or ''} de {where} est expirée depuis le {end}."
    if alert.rule.code == "DOSSIER":
        return f"Le dossier de {where} est incomplet ; l'AMM expire le {end}."
    if alert.rule.code == "DECISION":
        return (
            f"Le renouvellement de {where} est déposé sans décision "
            f"depuis plus de {alert.rule.offset_days} jours."
        )
    return (
        f"L'AMM de {amm.product.name} au {amm.country.name} expire le {end} "
        f"(deadline de dépôt : {deadline}). Aucun renouvellement déposé."
    )


def alert_link(alert: Alert) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/amms/{alert.amm_id}"


def dispatch(alert: Alert) -> list[Notification]:
    """Creates one Notification per recipient and channel; pushes in-app, emails via Celery."""
    from .tasks import send_alert_email

    title, body, link = alert_title(alert), alert_body(alert), alert_link(alert)
    channels = alert.rule.channels or ["IN_APP"]
    created: list[Notification] = []
    for user in recipients_for(alert):
        for channel in channels:
            if channel not in Notification.Channel.values:
                continue
            notification = Notification.objects.create(
                user=user,
                alert=alert,
                channel=channel,
                title=title,
                body=body,
                link=link,
                sent_at=timezone.now() if channel == Notification.Channel.IN_APP else None,
            )
            created.append(notification)
            if channel == Notification.Channel.IN_APP:
                publish_user_event(
                    user.pk, "notification.created", notification.pk, alert.amm.country.iso2
                )
            else:
                enqueue(send_alert_email, str(notification.pk))
    return created
