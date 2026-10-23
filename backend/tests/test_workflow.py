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


def test_correcting_a_renewal_date_reorders_and_recomputes(ceo_client, make_amm, make_renewal):
    from apps.amm.models import Renewal

    amm = make_amm(start=date(2012, 1, 1))
    first = make_renewal(amm, status="OBTENU", start_date=date(2017, 1, 1), number="R1")
    second = make_renewal(amm, status="OBTENU", start_date=date(2022, 1, 1), number="R2")
    # La date du « second » était fausse (décision de 2016) : corrigée, il passe en premier.
    response = ceo_client.patch(
        f"/api/v1/renewals/{second.pk}",
        {"start_date": "2016-06-01", "number": "R0"},
        format="json",
    )
    assert response.status_code == 200, response.content
    second.refresh_from_db()
    first.refresh_from_db()
    assert (second.sequence, first.sequence) == (1, 2)
    assert second.end_date is not None and second.number == "R0"
    amm.refresh_from_db()
    assert amm.effective_end_date == first.end_date
    assert Renewal.objects.filter(amm=amm).count() == 2


def test_correcting_a_start_date_recomputes_a_typed_end(ceo_client, make_amm, make_renewal):
    amm = make_amm(start=date(2019, 1, 1))
    renewal = make_renewal(
        amm,
        "OBTENU",
        number="R1",
        start_date=date(2024, 1, 1),
        end_date=date(2027, 7, 1),
        end_date_manual=True,
    )
    # Le formulaire renvoie la fin inchangée : la date de début corrigée refait le calcul.
    response = ceo_client.patch(
        f"/api/v1/renewals/{renewal.pk}",
        {"start_date": "2024-03-02", "end_date": "2027-07-01"},
        format="json",
    )
    assert response.status_code == 200, response.content
    renewal.refresh_from_db()
    assert renewal.end_date == date(2029, 3, 2) and not renewal.end_date_manual
    amm.original_end_date = date(2023, 5, 5)
    amm.original_end_date_manual = True
    amm.save()
    response = ceo_client.patch(
        f"/api/v1/amms/{amm.pk}",
        {"original_start_date": "2019-02-01", "original_end_date": "2023-05-05"},
        format="json",
    )
    assert response.status_code == 200, response.content
    amm.refresh_from_db()
    assert amm.original_end_date == date(2024, 2, 1) and not amm.original_end_date_manual


def test_typed_end_equal_to_the_computed_one_stays_computed(make_amm, make_renewal):
    amm = make_amm(start=date(2019, 1, 1))
    renewal = make_renewal(
        amm,
        "OBTENU",
        number="R1",
        start_date=date(2024, 1, 1),
        end_date=date(2029, 1, 1),
        end_date_manual=True,
    )
    assert not renewal.end_date_manual
    renewal.start_date = date(2024, 6, 1)
    renewal.save()
    assert renewal.end_date == date(2029, 6, 1)
