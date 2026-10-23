"""Règles de calcul relues (version 1.0.8) : fenêtres d'échéance, export, rappels."""

from datetime import date

import pytest

from apps.amm.models import MarketingAuthorization
from apps.amm.services.status import derive_status
from apps.analytics.services import export_rows, window_end
from apps.notifications.reminders import reminder_body

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("today", "end"),
    [(date(2026, 9, 30), date(2027, 3, 31)), (date(2027, 2, 28), date(2027, 8, 31))],
)
def test_six_month_window_matches_the_to_renew_status(today, end):
    assert derive_status(end, today) == "A_RENOUVELER"
    assert end <= window_end(today, 6)


def test_export_keeps_the_decision_in_force_after_a_planned_renewal(make_amm, make_renewal):
    amm = make_amm(start=date(2016, 1, 1))
    make_renewal(amm, "OBTENU", number="R1", start_date=date(2021, 1, 1))
    make_renewal(amm, "PLANIFIE")
    row = export_rows(MarketingAuthorization.objects.filter(pk=amm.pk))[0]
    assert row[6:9] == [date(2021, 1, 1), "R1", date(2026, 1, 1)]


def test_reminder_quotes_the_number_of_the_decision_that_expires(make_amm, make_renewal):
    amm = make_amm(start=date(2016, 1, 1), original_number="ORIG-2016")
    make_renewal(amm, "OBTENU", number="R-2021", start_date=date(2021, 1, 1))
    amm.refresh_from_db()
    body = reminder_body(amm, date(2025, 9, 1))
    assert "n° R-2021" in body and "ORIG-2016" not in body
