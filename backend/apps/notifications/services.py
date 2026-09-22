"""Fan-out of an alert to its recipients on each channel of the rule."""

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.alerts.models import Alert
from apps.core.tasks import enqueue
from apps.realtime.publisher import publish_user_event

from .models import Notification

SEVERITY_LABEL = {"INFO": "Info", "WARNING": "Attention", "CRITICAL": "Critique"}


def recipients_for(alert: Alert):
    """Active users with one of the rule roles: global roles, or scoped on the AMM country."""
    roles = alert.rule.roles or []
    return list(
        User.objects.filter(is_active=True, role__in=roles)
        .filter(Q(role__in=User.GLOBAL_ROLES) | Q(countries=alert.amm.country_id))
        .distinct()
    )


def alert_title(alert: Alert) -> str:
    amm = alert.amm
    label = SEVERITY_LABEL.get(alert.rule.severity, alert.rule.severity)
    return f"[{label}] {alert.rule.code} — {amm.product.name} ({amm.country.iso2})"


def _fr(value) -> str:
    return value.strftime("%d/%m/%Y") if value else "inconnue"


def alert_body(alert: Alert) -> str:
    amm = alert.amm
    end = _fr(amm.effective_end_date)
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
        f"(Dépôt idéal : {_fr(amm.ideal_filing_date)} ; "
        f"Limite agence : {_fr(amm.agency_filing_deadline)}). Aucun renouvellement déposé."
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
