"""Rappel quotidien des AMM « À renouveler » (règle 4 du responsable).

Chaque jour, tant qu'une AMM est « À renouveler » (dans les six mois précédant sa fin, non
expirée), ses réglementaires (siège et pays de l'AMM) reçoivent un rappel. Au plus un par AMM,
par destinataire, par canal et par jour : relancer la tâche le même jour ne crée rien de plus.
Le rappel s'arrête de lui-même quand l'AMM n'est plus « À renouveler » : un renouvellement
obtenu repousse la fin (elle redevient « Valide »), ou la fin est dépassée (« Expirée »).
"""

from datetime import date

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User
from apps.amm.models import MarketingAuthorization
from apps.amm.services.status import (
    RENEWAL_WINDOW_MONTHS,
    STATUS_A_RENOUVELER,
    compute_amm_state,
    current_scans_prefetch,
)
from apps.core.dates import today as reference_today
from apps.core.tasks import enqueue
from apps.realtime.publisher import publish_user_event

from .models import Notification

REGULATORY_ROLES = (User.Role.HQ_REGULATORY, User.Role.COUNTRY_REGULATORY)


def _fr(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def reminder_recipients(amm) -> list[User]:
    """Réglementaires actifs : le siège, et les réglementaires pays rattachés au pays de l'AMM."""
    return list(
        User.objects.filter(is_active=True, role__in=REGULATORY_ROLES)
        .filter(Q(role=User.Role.HQ_REGULATORY) | Q(countries=amm.country_id))
        .distinct()
    )


def reminder_title(amm) -> str:
    return (
        f"À renouveler — {amm.product.name} ({amm.country.iso2}) : "
        f"expire le {_fr(amm.effective_end_date)}"
    )


def reminder_body(amm, today: date) -> str:
    ideal, agency = amm.ideal_filing_date, amm.agency_filing_deadline
    ideal_text = f"{_fr(ideal)} (dépassé)" if today > ideal else _fr(ideal)
    agency_text = f"{_fr(agency)} (dépassée)" if today > agency else _fr(agency)
    number = f" n° {amm.original_number}" if amm.original_number else ""
    return "\n".join(
        [
            f"L'AMM{number} de {amm.product.name} au {amm.country.name} "
            f"expire le {_fr(amm.effective_end_date)}.",
            f"Dépôt idéal : {ideal_text}",
            f"Limite agence : {agency_text}",
            "Ce rappel est envoyé chaque jour tant que l'AMM est « À renouveler ».",
        ]
    )


def reminder_channels() -> list[str]:
    channels = getattr(settings, "RENEWAL_REMINDER_CHANNELS", [Notification.Channel.IN_APP])
    return [c for c in channels if c in Notification.Channel.values]


def _create_once(user, amm, channel, today, title, body, link) -> Notification | None:
    """Crée le rappel du jour, ou None s'il existe déjà (idempotence, contrainte unique)."""
    in_app = channel == Notification.Channel.IN_APP
    try:
        with transaction.atomic():
            notification, created = Notification.objects.get_or_create(
                user=user,
                amm=amm,
                channel=channel,
                reminder_date=today,
                defaults={
                    "title": title[:255],
                    "body": body,
                    "link": link,
                    "sent_at": timezone.now() if in_app else None,
                },
            )
    except IntegrityError:  # course avec une autre exécution du même jour
        return None
    return notification if created else None


def send_renewal_reminders(today: date | None = None) -> dict:
    """Crée les rappels du jour. Returns {"amms", "created", "skipped"}."""
    from .tasks import send_alert_email

    today = today or reference_today()
    channels = reminder_channels()
    link_base = settings.FRONTEND_URL.rstrip("/")
    # Candidates : fin dans la fenêtre de six mois. L'état est recalculé ici même, pour ne pas
    # dépendre de l'heure du recalcul nocturne.
    queryset = (
        MarketingAuthorization.objects.filter(
            effective_end_date__gte=today,
            effective_end_date__lte=today + relativedelta(months=RENEWAL_WINDOW_MONTHS + 1),
        )
        .select_related("country", "product")
        .prefetch_related("renewals", current_scans_prefetch())
    )
    amms = created = skipped = 0
    for amm in queryset.iterator(chunk_size=200):
        state = compute_amm_state(
            amm, today=today, renewals=list(amm.renewals.all()), documents=amm.current_scans
        )
        if state.status != STATUS_A_RENOUVELER:
            continue
        state.apply_to(amm)
        amms += 1
        title, body = reminder_title(amm), reminder_body(amm, today)
        link = f"{link_base}/amms/{amm.pk}"
        for user in reminder_recipients(amm):
            for channel in channels:
                notification = _create_once(user, amm, channel, today, title, body, link)
                if notification is None:
                    skipped += 1
                    continue
                created += 1
                if channel == Notification.Channel.IN_APP:
                    publish_user_event(
                        user.pk, "notification.created", notification.pk, amm.country.iso2
                    )
                else:
                    enqueue(send_alert_email, str(notification.pk))
    return {"amms": amms, "created": created, "skipped": skipped}
