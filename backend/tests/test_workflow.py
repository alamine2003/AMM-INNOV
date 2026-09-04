"""Renewal state machine."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.amm.services.workflow import allowed_transitions, transition

pytestmark = pytest.mark.django_db


def test_happy_path_to_obtenu(make_amm, make_renewal):
    amm = make_amm(start=date(2019, 1, 1))
    renewal = make_renewal(amm)
    transition(renewal, "EN_PREPARATION")
    transition(renewal, "DEPOSE", filing_date=date(2026, 1, 15))
    transition(renewal, "EN_INSTRUCTION")
    transition(renewal, "OBTENU", number="R-2026", start_date=date(2026, 6, 1))
    renewal.refresh_from_db()
    assert renewal.workflow_status == "OBTENU"
    assert renewal.end_date == date(2031, 6, 1)
    amm.refresh_from_db()
    assert amm.status == "VALIDE" and amm.effective_end_date == date(2031, 6, 1)


def test_depose_directly_to_obtenu_allowed(make_amm, make_renewal):
    renewal = make_renewal(make_amm(), "DEPOSE", filing_date=date(2026, 1, 1))
    transition(renewal, "OBTENU", number="N", start_date=date(2026, 5, 1))
    assert renewal.workflow_status == "OBTENU"


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        ("PLANIFIE", "DEPOSE"),
        ("PLANIFIE", "OBTENU"),
        ("EN_PREPARATION", "EN_INSTRUCTION"),
        ("DEPOSE", "REJETE"),
        ("OBTENU", "ABANDONNE"),
        ("REJETE", "DEPOSE"),
        ("ABANDONNE", "PLANIFIE"),
        ("DEPOSE", "PLANIFIE"),
    ],
)
def test_invalid_transitions(make_amm, make_renewal, from_status, to_status):
    renewal = make_renewal(
        make_amm(),
        from_status,
        filing_date=date(2026, 1, 1),
        number="N",
        start_date=date(2026, 1, 1),
    )
    with pytest.raises(ValidationError):
        transition(renewal, to_status)


def test_depose_requires_filing_date(make_amm, make_renewal):
    renewal = make_renewal(make_amm(), "EN_PREPARATION")
    with pytest.raises(ValidationError) as exc:
        transition(renewal, "DEPOSE")
    assert "filing_date" in exc.value.message_dict


def test_obtenu_requires_number_and_start_date(make_amm, make_renewal):
    renewal = make_renewal(make_amm(), "EN_INSTRUCTION", filing_date=date(2026, 1, 1))
    with pytest.raises(ValidationError) as exc:
        transition(renewal, "OBTENU", number="R")
    assert "start_date" in exc.value.message_dict


def test_abandon_from_any_open_state(make_amm, make_renewal):
    for status in ("PLANIFIE", "EN_PREPARATION", "DEPOSE", "EN_INSTRUCTION"):
        renewal = make_renewal(make_amm(), status, filing_date=date(2026, 1, 1))
        transition(renewal, "ABANDONNE")
        assert renewal.workflow_status == "ABANDONNE"
        assert allowed_transitions(renewal) == set()


def test_unknown_target_status(make_amm, make_renewal):
    with pytest.raises(ValidationError):
        transition(make_renewal(make_amm()), "FOO")
