"""compute_amm_state: statuses, urgencies at the boundaries, automatic end dates."""

from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from apps.amm.models import Renewal
from apps.amm.services.status import compute_amm_state
from tests.conftest import TODAY

pytestmark = pytest.mark.django_db


M = relativedelta
D = timedelta


@pytest.mark.parametrize(
    ("to_end", "expected_status", "expected_urgency"),
    [
        (D(days=400), "VALIDE", "OK"),
        (D(days=366), "VALIDE", "OK"),
        (D(days=365), "VALIDE", "A_PLANIFIER"),
        (M(months=6, days=1), "VALIDE", "A_PLANIFIER"),  # veille de la fenêtre des 6 mois
        (M(months=6), "A_RENOUVELER", "DEPOT_URGENT"),  # fin − 6 mois = aujourd'hui (jour J)
        (M(months=3, days=1), "A_RENOUVELER", "DEPOT_URGENT"),  # limite agence demain
        (M(months=3), "A_RENOUVELER", "CRITIQUE"),  # limite agence = aujourd'hui
        (D(days=1), "A_RENOUVELER", "CRITIQUE"),
        (D(days=0), "A_RENOUVELER", "CRITIQUE"),  # fin = aujourd'hui : encore valide
        (D(days=-1), "EXPIRE", "EXPIRE"),  # fin + 1 jour : expirée
        (D(days=-500), "EXPIRE", "EXPIRE"),
    ],
)
def test_status_and_urgency_from_original_end_date(
    make_amm, to_end, expected_status, expected_urgency
):
    end = TODAY + to_end
    amm = make_amm(original_start_date=None, original_end_date=end, original_end_date_manual=True)
    state = compute_amm_state(amm, today=TODAY)
    assert (state.status, state.urgency) == (expected_status, expected_urgency)
    assert state.effective_end_date == end
    assert state.ideal_filing_date == end - relativedelta(months=6)
    assert state.agency_filing_deadline == end - relativedelta(months=3)
    amm.refresh_from_db()
    assert amm.status == expected_status and amm.urgency == expected_urgency
    assert amm.ideal_filing_date == state.ideal_filing_date
    assert amm.agency_filing_deadline == state.agency_filing_deadline


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2027, 1, 14), "VALIDE"),  # veille de fin − 6 mois
        (date(2027, 1, 15), "A_RENOUVELER"),  # fin − 6 mois, jour J
        (date(2027, 7, 15), "A_RENOUVELER"),  # fin = aujourd'hui : encore valide
        (date(2027, 7, 16), "EXPIRE"),  # fin + 1
    ],
)
def test_exact_boundaries(make_amm, today, expected):
    amm = make_amm(
        original_start_date=None, original_end_date=date(2027, 7, 15), original_end_date_manual=True
    )
    assert compute_amm_state(amm, today=today).status == expected


def test_filing_dates_are_ideal_six_months_and_agency_three_months(make_amm):
    amm = make_amm(
        original_start_date=None, original_end_date=date(2027, 8, 31), original_end_date_manual=True
    )
    assert amm.ideal_filing_date == date(2027, 2, 28)
    assert amm.agency_filing_deadline == date(2027, 5, 31)


def test_end_date_auto_computed_with_five_years(make_amm):
    amm = make_amm(start=date(2024, 2, 29))
    assert amm.original_end_date == date(2029, 2, 28)
    assert amm.effective_end_date == date(2029, 2, 28)
    assert amm.ideal_filing_date == date(2028, 8, 28)
    assert amm.agency_filing_deadline == date(2028, 11, 28)
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
    assert amm.effective_end_date is None
    assert amm.ideal_filing_date is None and amm.agency_filing_deadline is None


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


def test_expired_even_with_a_filing_in_progress(make_amm, make_renewal):
    """Règle 3 : un dépôt en cours n'empêche pas l'expiration (plus de statut IN_PROCESS)."""
    amm = make_amm(start=date(2018, 1, 1))
    for workflow in ("PLANIFIE", "EN_PREPARATION", "DEPOSE", "EN_INSTRUCTION"):
        Renewal.objects.filter(amm=amm).delete()
        make_renewal(amm, workflow, filing_date=date(2026, 1, 1))
        amm.refresh_from_db()
        assert (amm.status, amm.urgency) == ("EXPIRE", "EXPIRE"), workflow


def test_filing_in_progress_without_any_date_is_unknown(make_amm, make_renewal):
    amm = make_amm(original_start_date=None)
    make_renewal(amm, "EN_INSTRUCTION", filing_date=date(2026, 1, 1))
    amm.refresh_from_db()
    assert amm.status == "INDETERMINE"
    assert amm.get_status_display() == "Échéance inconnue"


def test_pending_renewal_does_not_change_status_nor_urgency(make_amm, make_renewal):
    amm = make_amm(start=TODAY - timedelta(days=365 * 5 - 100))
    before = (amm.status, amm.urgency)
    assert before == ("A_RENOUVELER", "DEPOT_URGENT")
    make_renewal(amm, "DEPOSE", filing_date=TODAY)
    amm.refresh_from_db()
    assert (amm.status, amm.urgency) == before


@pytest.mark.parametrize("workflow", ["PLANIFIE", "DEPOSE", "EN_INSTRUCTION", "REJETE"])
def test_renewal_not_obtained_is_ignored(make_amm, make_renewal, workflow):
    """Règle 1 : seul un renouvellement OBTENU compte, même s'il porte des dates."""
    amm = make_amm(start=date(2018, 1, 1))
    renewal = make_renewal(amm, "OBTENU", number="R-1", start_date=date(2023, 1, 1))
    Renewal.objects.filter(pk=renewal.pk).update(workflow_status=workflow)
    amm.refresh_from_db()
    state = compute_amm_state(amm, today=TODAY)
    assert state.effective_end_date == amm.original_end_date == date(2023, 1, 1)
    assert state.status == "EXPIRE"


def test_obtained_renewal_moves_the_end_and_leaves_the_window(make_amm, make_renewal):
    amm = make_amm(start=TODAY - timedelta(days=365 * 5 - 60))
    assert amm.status == "A_RENOUVELER"
    make_renewal(amm, "OBTENU", number="R-1", start_date=TODAY)
    amm.refresh_from_db()
    assert amm.status == "VALIDE" and amm.urgency == "OK"
    assert amm.effective_end_date == TODAY + relativedelta(years=5)


def test_renewal_end_date_auto_and_sequence(make_amm, make_renewal):
    amm = make_amm(country="GN", start=date(2020, 1, 1))
    first = make_renewal(amm, "PLANIFIE")
    second = Renewal.objects.create(
        amm=amm, workflow_status="OBTENU", number="X", start_date=date(2023, 1, 1)
    )
    assert (first.sequence, second.sequence) == (1, 2)
    assert second.end_date == date(2026, 1, 1)
