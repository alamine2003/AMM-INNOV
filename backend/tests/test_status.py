"""compute_amm_state: statuses, urgencies at the boundaries, automatic end dates."""

from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from apps.amm.models import Renewal
from apps.amm.services.status import compute_amm_state
from tests.conftest import TODAY

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("days_to_end", "expected_status", "expected_urgency"),
    [
        (400, "VALIDE", "OK"),
        (366, "VALIDE", "OK"),
        (365, "VALIDE", "A_PLANIFIER"),
        (200, "VALIDE", "A_PLANIFIER"),
        (181, "VALIDE", "A_PLANIFIER"),
        (180, "VALIDE", "DEPOT_URGENT"),
        (91, "VALIDE", "DEPOT_URGENT"),
        (90, "VALIDE", "CRITIQUE"),
        (1, "VALIDE", "CRITIQUE"),
        (0, "VALIDE", "CRITIQUE"),
        (-1, "EXPIRE", "EXPIRE"),
        (-500, "EXPIRE", "EXPIRE"),
    ],
)
def test_status_and_urgency_from_original_end_date(
    make_amm, days_to_end, expected_status, expected_urgency
):
    amm = make_amm(
        original_start_date=None,
        original_end_date=TODAY + timedelta(days=days_to_end),
        original_end_date_manual=True,
    )
    state = compute_amm_state(amm, today=TODAY)
    assert (state.status, state.urgency) == (expected_status, expected_urgency)
    assert state.effective_end_date == TODAY + timedelta(days=days_to_end)
    assert state.filing_deadline == state.effective_end_date - relativedelta(months=6)
    amm.refresh_from_db()
    assert amm.status == expected_status and amm.urgency == expected_urgency


def test_end_date_auto_computed_with_five_years(make_amm):
    amm = make_amm(start=date(2024, 2, 29))
    assert amm.original_end_date == date(2029, 2, 28)
    assert amm.effective_end_date == date(2029, 2, 28)
    assert amm.filing_deadline == date(2028, 8, 28)
    assert amm.status == "VALIDE"


def test_end_date_uses_country_validity_years(make_amm):
    amm = make_amm(country="GN", start=date(2025, 1, 10))
    assert amm.original_end_date == date(2028, 1, 10)


def test_manual_end_date_wins(make_amm):
    amm = make_amm(
        start=date(2025, 1, 10), original_end_date=date(2027, 1, 10), original_end_date_manual=True
    )
    assert amm.original_end_date == date(2027, 1, 10)
    assert amm.effective_end_date == date(2027, 1, 10)


def test_indetermine_without_dates(make_amm):
    amm = make_amm(original_start_date=None)
    assert amm.status == "INDETERMINE"
    assert amm.urgency == "A_PLANIFIER"
    assert amm.effective_end_date is None and amm.filing_deadline is None


def test_valid_through_obtained_renewal(make_amm, make_renewal):
    amm = make_amm(start=date(2018, 1, 1))
    assert amm.status == "EXPIRE"
    make_renewal(amm, "OBTENU", number="R-1", start_date=date(2024, 6, 1))
    amm.refresh_from_db()
    assert amm.status == "VALIDE"
    assert amm.effective_end_date == date(2029, 6, 1)
    assert amm.urgency == "OK"


def test_most_recent_obtained_renewal_wins(make_amm, make_renewal):
    amm = make_amm(start=date(2010, 1, 1))
    make_renewal(amm, "OBTENU", number="R-1", start_date=date(2015, 1, 1))
    make_renewal(amm, "OBTENU", number="R-2", start_date=date(2020, 1, 1))
    amm.refresh_from_db()
    assert amm.effective_end_date == date(2025, 1, 1)
    assert amm.status == "EXPIRE"


def test_in_process_with_past_end_date(make_amm, make_renewal):
    amm = make_amm(start=date(2018, 1, 1))
    make_renewal(amm, "DEPOSE", filing_date=date(2026, 1, 1))
    amm.refresh_from_db()
    assert amm.status == "IN_PROCESS"
    assert amm.urgency == "EN_INSTRUCTION"


def test_in_process_without_any_date(make_amm, make_renewal):
    amm = make_amm(original_start_date=None)
    make_renewal(amm, "EN_INSTRUCTION", filing_date=date(2026, 1, 1))
    amm.refresh_from_db()
    assert amm.status == "IN_PROCESS"


def test_pending_renewal_with_valid_end_date_stays_valid(make_amm, make_renewal):
    amm = make_amm(start=TODAY - timedelta(days=365 * 5 - 100))
    make_renewal(amm, "DEPOSE", filing_date=TODAY)
    amm.refresh_from_db()
    assert amm.status == "VALIDE"
    assert amm.urgency == "EN_INSTRUCTION"


def test_renewal_end_date_auto_and_sequence(make_amm, make_renewal):
    amm = make_amm(country="GN", start=date(2020, 1, 1))
    first = make_renewal(amm, "PLANIFIE")
    second = Renewal.objects.create(
        amm=amm, workflow_status="OBTENU", number="X", start_date=date(2023, 1, 1)
    )
    assert (first.sequence, second.sequence) == (1, 2)
    assert second.end_date == date(2026, 1, 1)
