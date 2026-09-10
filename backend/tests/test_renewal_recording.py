"""Ajout d'un renouvellement en une étape : l'AMM est recalculée automatiquement."""

from datetime import date

import pytest

from apps.amm.history import amm_history
from apps.amm.models import MarketingAuthorization, Renewal

from .conftest import TODAY

pytestmark = pytest.mark.django_db

EXPIRED_START = date(2019, 1, 1)  # + 5 ans => 2024-01-01, expirée au 04/09/2026


def record(client, amm, **payload):
    """La saisie minimale : un numéro et une date de début. Le statut n'est pas envoyé."""
    body = {"number": "SN-2026-0042", "start_date": "2026-08-01"}
    body.update(payload)
    return client.post(f"/api/v1/amms/{amm.pk}/renewals", body, format="json")


def test_recording_an_obtained_renewal_turns_an_expired_amm_valid(hq_client, users, make_amm):
    amm = make_amm(country="SN", start=EXPIRED_START)
    assert amm.status == MarketingAuthorization.Status.EXPIRE

    response = record(hq_client, amm)
    assert response.status_code == 201, response.data
    assert response.data["workflow_status"] == "OBTENU"
    # Échéance dérivée de la durée de validité du pays (5 ans), sans saisie manuelle.
    assert response.data["end_date"] == "2031-08-01"
    assert response.data["end_date_manual"] is False

    amm.refresh_from_db()
    assert amm.status == MarketingAuthorization.Status.VALIDE
    assert amm.urgency == MarketingAuthorization.Urgency.OK
    assert amm.effective_end_date == date(2031, 8, 1)
    assert amm.filing_deadline == date(2031, 2, 1)  # 6 mois avant l'échéance
    # La date d'origine reste la mémoire de l'AMM initiale.
    assert amm.original_start_date == EXPIRED_START and amm.original_end_date == date(2024, 1, 1)

    entries = amm_history(amm)
    assert any(
        entry["model"] == "renewal" and entry["user_email"] == users["hq"].email
        for entry in entries
    ), entries
    assert any(
        change["field"] == "status" and change["new"] == "VALIDE"
        for entry in entries
        if entry["model"] == "amm"
        for change in entry["changes"]
    ), entries


def test_country_validity_period_drives_the_computed_end_date(hq_client, make_amm):
    amm = make_amm(country="GN", start=EXPIRED_START)  # Guinée : 3 ans
    response = record(hq_client, amm)
    assert response.status_code == 201, response.data
    assert response.data["end_date"] == "2029-08-01"
    amm.refresh_from_db()
    assert amm.effective_end_date == date(2029, 8, 1)


def test_explicit_end_date_overrides_the_computation(hq_client, make_amm):
    amm = make_amm(country="SN", start=EXPIRED_START)
    response = record(hq_client, amm, end_date="2028-03-15")
    assert response.status_code == 201, response.data
    assert response.data["end_date"] == "2028-03-15"
    assert response.data["end_date_manual"] is True
    amm.refresh_from_db()
    assert amm.effective_end_date == date(2028, 3, 15)
    assert amm.status == MarketingAuthorization.Status.VALIDE


def test_a_decision_already_expired_does_not_revive_the_amm(hq_client, make_amm):
    amm = make_amm(country="SN", start=EXPIRED_START)
    response = record(hq_client, amm, start_date="2018-01-01")
    assert response.status_code == 201, response.data
    amm.refresh_from_db()
    assert amm.effective_end_date == date(2023, 1, 1)
    assert amm.status == MarketingAuthorization.Status.EXPIRE
    assert amm.urgency == MarketingAuthorization.Urgency.EXPIRE


def test_a_dated_decision_still_needs_its_number(hq_client, make_amm):
    amm = make_amm(country="SN", start=EXPIRED_START)
    assert record(hq_client, amm, number="").status_code == 400
    assert not Renewal.objects.filter(amm=amm).exists()
    amm.refresh_from_db()
    assert amm.status == MarketingAuthorization.Status.EXPIRE


def test_a_renewal_without_a_start_date_is_only_planned(hq_client, make_amm):
    """Sans date, il n'y a pas de décision : on planifie, et l'AMM reste expirée."""
    amm = make_amm(country="SN", start=EXPIRED_START)
    response = record(hq_client, amm, start_date=None)
    assert response.status_code == 201, response.data
    assert response.data["workflow_status"] == "PLANIFIE"
    amm.refresh_from_db()
    assert amm.status == MarketingAuthorization.Status.EXPIRE


def test_an_open_renewal_is_completed_by_its_decision(hq_client, make_amm, make_renewal):
    """Le dépôt en cours aboutit : même renouvellement, même n° d'ordre, dépôt conservé."""
    amm = make_amm(country="SN", start=EXPIRED_START)
    pending = make_renewal(amm, "DEPOSE", filing_date=date(2026, 3, 1))
    response = record(hq_client, amm)
    assert response.status_code == 201, response.data
    assert Renewal.objects.filter(amm=amm).count() == 1
    pending.refresh_from_db()
    assert pending.workflow_status == "OBTENU" and pending.sequence == 1
    assert pending.filing_date == date(2026, 3, 1)
    assert pending.number == "SN-2026-0042" and pending.end_date == date(2031, 8, 1)
    amm.refresh_from_db()
    assert amm.status == MarketingAuthorization.Status.VALIDE


def test_a_second_plan_is_refused_while_one_is_open(hq_client, make_amm, make_renewal):
    amm = make_amm(country="SN", start=EXPIRED_START)
    make_renewal(amm, "DEPOSE", filing_date=date(2026, 3, 1))
    response = hq_client.post(f"/api/v1/amms/{amm.pk}/renewals", {}, format="json")
    assert response.status_code == 400
    assert "déjà en cours" in str(response.data)
    assert Renewal.objects.filter(amm=amm).count() == 1


def test_the_workflow_route_still_creates_a_planned_renewal(hq_client, make_amm):
    amm = make_amm(country="SN", start=EXPIRED_START)
    response = hq_client.post(f"/api/v1/amms/{amm.pk}/renewals", {}, format="json")
    assert response.status_code == 201, response.data
    assert response.data["workflow_status"] == "PLANIFIE"
    assert response.data["allowed_transitions"] == ["ABANDONNE", "EN_PREPARATION"]
    amm.refresh_from_db()
    assert amm.status == MarketingAuthorization.Status.EXPIRE


def test_a_country_user_cannot_record_outside_its_scope(country_client, make_amm):
    outside = make_amm(country="CI", start=EXPIRED_START)
    assert record(country_client, outside).status_code == 404
    assert not Renewal.objects.filter(amm=outside).exists()

    inside = make_amm(country="SN", start=EXPIRED_START)
    assert record(country_client, inside).status_code == 201
    inside.refresh_from_db()
    assert inside.status == MarketingAuthorization.Status.VALIDE


def test_recording_resolves_the_open_alerts_of_the_amm(hq_client, make_amm, rules):
    from apps.alerts.models import Alert
    from apps.alerts.services.engine import evaluate_rules

    amm = make_amm(country="SN", start=date(2021, 12, 1))  # échéance 2026-12-01 : J-180 franchi
    evaluate_rules(today=TODAY)
    assert Alert.objects.filter(amm=amm, status=Alert.Status.OPEN).exists()

    assert record(hq_client, amm).status_code == 201
    assert not Alert.objects.filter(amm=amm, status__in=Alert.OPEN_STATUSES).exists()
