"""Rappel quotidien « À renouveler » (règle 4) : destinataires, texte, idempotence, arrêt."""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.test import override_settings

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.tasks import send_renewal_reminders
from tests.conftest import TODAY

pytestmark = pytest.mark.django_db


def to_renew(make_amm, **kwargs):
    """Fin le 01/12/2026 : dans les six mois, dépôt idéal (01/06) dépassé, limite (01/09) aussi."""
    return make_amm(start=date(2021, 12, 1), **kwargs)


def reminders(amm=None):
    queryset = Notification.objects.filter(reminder_date__isnull=False)
    return queryset.filter(amm=amm) if amm else queryset


def test_daily_reminder_goes_to_hq_and_country_regulatory(users, make_amm, countries):
    amm = to_renew(make_amm, country="SN")
    other_country = User.objects.create_user(
        "ci@test.local", "Passw0rd!", role=User.Role.COUNTRY_REGULATORY
    )
    other_country.countries.set([countries["CI"]])
    result = send_renewal_reminders(TODAY.isoformat())
    assert result["amms"] == 1
    in_app = reminders(amm).filter(channel=Notification.Channel.IN_APP)
    # Siège + réglementaire du pays ; ni le CEO, ni le réglementaire d'un autre pays.
    assert {n.user for n in in_app} == {users["hq"], users["country"]}
    note = in_app.first()
    assert note.title.startswith("À renouveler — ") and "(SN)" in note.title
    assert "expire le 01/12/2026" in note.title and "expire le 01/12/2026" in note.body
    assert "Dépôt idéal : 01/06/2026 (dépassé)" in note.body
    assert "Limite agence : 01/09/2026 (dépassée)" in note.body
    assert note.link.endswith(f"/amms/{amm.pk}") and note.sent_at is not None
    # E-mail comme les alertes (canaux configurables) : un par destinataire.
    assert sorted(m.to[0] for m in mail.outbox) == sorted([users["hq"].email, "sn@test.local"])


def test_future_dates_are_shown_without_passed_mention(users, make_amm):
    # Fin le 01/02/2027 : dépôt idéal 01/08/2026 dépassé, limite agence 01/11/2026 à venir.
    amm = make_amm(start=date(2022, 2, 1))
    assert amm.status == "A_RENOUVELER"
    send_renewal_reminders(TODAY.isoformat())
    body = reminders(amm).first().body
    assert "Dépôt idéal : 01/08/2026 (dépassé)" in body
    assert "Limite agence : 01/11/2026\n" in body


def test_reminder_is_idempotent_within_a_day_and_repeats_the_next_day(users, make_amm):
    amm = to_renew(make_amm)
    send_renewal_reminders(TODAY.isoformat())
    count = reminders(amm).count()
    assert count == 4  # 2 destinataires × (in-app + e-mail)
    again = send_renewal_reminders(TODAY.isoformat())
    assert again["created"] == 0 and again["skipped"] == 4
    assert reminders(amm).count() == count and len(mail.outbox) == 2
    # Insistant : le lendemain, un nouveau rappel.
    send_renewal_reminders((TODAY + timedelta(days=1)).isoformat())
    assert reminders(amm).count() == 2 * count


@override_settings(RENEWAL_REMINDER_CHANNELS=["IN_APP"])
def test_email_can_be_switched_off(users, make_amm):
    to_renew(make_amm)
    send_renewal_reminders(TODAY.isoformat())
    assert reminders().count() == 2 and not mail.outbox


def test_no_reminder_for_valid_expired_or_unknown(users, make_amm):
    make_amm(start=date(2025, 1, 1))  # valide, fin 2030
    make_amm(start=date(2015, 1, 1))  # expirée
    make_amm(original_start_date=None)  # échéance inconnue
    assert send_renewal_reminders(TODAY.isoformat())["amms"] == 0
    assert not reminders().exists()


def test_reminder_stops_when_an_obtained_renewal_moves_the_end(users, make_amm, make_renewal):
    amm = to_renew(make_amm)
    send_renewal_reminders(TODAY.isoformat())
    make_renewal(amm, "DEPOSE", filing_date=TODAY)
    # Un dépôt ne suffit pas : l'AMM reste « À renouveler », le rappel continue.
    tomorrow = TODAY + timedelta(days=1)
    assert send_renewal_reminders(tomorrow.isoformat())["amms"] == 1
    renewal = amm.renewals.get()
    renewal.workflow_status = "OBTENU"
    renewal.number = "R-1"
    renewal.start_date = TODAY
    renewal.save()
    amm.refresh_from_db()
    assert amm.status == "VALIDE"
    before = reminders(amm).count()
    assert send_renewal_reminders((TODAY + timedelta(days=2)).isoformat())["amms"] == 0
    assert reminders(amm).count() == before


def test_reminder_stops_once_expired(users, make_amm):
    amm = to_renew(make_amm)  # fin le 01/12/2026
    assert send_renewal_reminders("2026-12-01")["amms"] == 1  # fin = aujourd'hui : encore valide
    before = reminders(amm).count()
    assert send_renewal_reminders("2026-12-02")["amms"] == 0
    assert reminders(amm).count() == before


def test_reminder_is_listed_with_its_amm(users, make_amm, country_client):
    amm = to_renew(make_amm)
    send_renewal_reminders(TODAY.isoformat())
    items = country_client.get("/api/v1/notifications").json()
    items = items["results"] if isinstance(items, dict) else items
    note = next(n for n in items if n["channel"] == "IN_APP")
    assert note["amm_id"] == str(amm.pk) and note["reminder_date"] == TODAY.isoformat()
    assert note["severity"] == "WARNING" and note["alert_id"] is None


def test_reminder_is_scheduled_daily():
    from celery.schedules import crontab
    from django.conf import settings

    entry = settings.CELERY_BEAT_SCHEDULE["send-renewal-reminders"]
    assert entry["task"] == "apps.notifications.tasks.send_renewal_reminders"
    schedule = entry["schedule"]
    assert isinstance(schedule, crontab) and schedule.day_of_week == set(range(7))
