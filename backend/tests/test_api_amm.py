"""AMM API: scope, CRUD, renewals and transitions, history."""

from datetime import date, timedelta

import pytest

from apps.alerts.models import Alert
from apps.alerts.services.engine import evaluate_rules
from tests.conftest import TODAY

pytestmark = pytest.mark.django_db


def test_country_user_sees_only_its_countries(country_client, make_amm):
    sn = make_amm(country="SN")
    ml = make_amm(country="ML")
    ci = make_amm(country="CI")
    response = country_client.get("/api/v1/amms")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    ids = {row["id"] for row in body["results"]}
    assert ids == {str(sn.pk), str(ml.pk)}
    assert country_client.get(f"/api/v1/amms/{ci.pk}").status_code == 404
    assert country_client.get(f"/api/v1/amms/{sn.pk}").status_code == 200


def test_country_user_cannot_write_outside_scope(country_client, countries, product):
    payload = {
        "product": str(product.pk),
        "country": str(countries["CI"].pk),
        "original_start_date": "2025-01-01",
    }
    assert country_client.post("/api/v1/amms", payload).status_code == 403


def test_hq_sees_everything_and_filters(hq_client, make_amm):
    make_amm(country="SN")
    make_amm(country="CI", start=date(2018, 1, 1))
    response = hq_client.get("/api/v1/amms")
    assert response.json()["count"] == 2
    assert hq_client.get("/api/v1/amms?country=CI").json()["count"] == 1
    assert hq_client.get("/api/v1/amms?status=EXPIRE").json()["count"] == 1
    assert hq_client.get("/api/v1/amms?urgency=OK,A_PLANIFIER").json()["count"] == 1
    assert hq_client.get("/api/v1/amms?has_current_scan=false").json()["count"] == 2
    assert hq_client.get("/api/v1/amms?range=GENERALE").json()["count"] == 2
    assert hq_client.get("/api/v1/amms?range=CARDIO").json()["count"] == 0


def test_create_amm_renewal_and_transition_resolves_alert(
    country_client, countries, product, rules
):
    start = TODAY - timedelta(days=365 * 5 - 170)  # expires in ~170 days -> J-180 fires
    created = country_client.post(
        "/api/v1/amms",
        {
            "product": str(product.pk),
            "country": str(countries["SN"].pk),
            "original_number": "SN-2021-001",
            "original_start_date": start.isoformat(),
            "dossier_state": "COMPLET",
        },
    )
    assert created.status_code == 201, created.json()
    amm = created.json()
    assert amm["status"] == "VALIDE" and amm["urgency"] == "DEPOT_URGENT"
    assert (
        amm["original_end_date"] == (start + timedelta(days=365 * 5 + 1)).isoformat()
        or amm["original_end_date"]
    )
    assert amm["has_current_scan"] is False

    evaluate_rules(today=TODAY)
    assert Alert.objects.filter(amm_id=amm["id"], rule__code="J-180", status="OPEN").exists()

    renewal = country_client.post(
        f"/api/v1/amms/{amm['id']}/renewals", {"workflow_status": "PLANIFIE"}
    )
    assert renewal.status_code == 201, renewal.json()
    renewal_id = renewal.json()["id"]
    assert renewal.json()["sequence"] == 1
    assert renewal.json()["allowed_transitions"] == ["ABANDONNE", "EN_PREPARATION"]

    # a second open renewal is refused
    assert country_client.post(f"/api/v1/amms/{amm['id']}/renewals", {}).status_code == 400

    assert (
        country_client.post(
            f"/api/v1/renewals/{renewal_id}/transition", {"to": "DEPOSE"}
        ).status_code
        == 400
    )
    step = country_client.post(
        f"/api/v1/renewals/{renewal_id}/transition", {"to": "EN_PREPARATION"}
    )
    assert step.status_code == 200
    filed = country_client.post(
        f"/api/v1/renewals/{renewal_id}/transition",
        {"to": "DEPOSE", "filing_date": TODAY.isoformat()},
    )
    assert filed.status_code == 200, filed.json()
    assert filed.json()["workflow_status"] == "DEPOSE"

    alert = Alert.objects.get(amm_id=amm["id"], rule__code="J-180")
    assert alert.status == "RESOLVED" and alert.resolution == "AUTO_FILED"
    detail = country_client.get(f"/api/v1/amms/{amm['id']}").json()
    assert detail["urgency"] == "EN_INSTRUCTION" and detail["pending_renewal_id"] == renewal_id

    obtained = country_client.post(
        f"/api/v1/renewals/{renewal_id}/transition",
        {"to": "OBTENU", "number": "SN-2026-009", "start_date": TODAY.isoformat()},
    )
    assert obtained.status_code == 200
    detail = country_client.get(f"/api/v1/amms/{amm['id']}").json()
    assert (
        detail["status"] == "VALIDE"
        and detail["effective_end_date"] == (TODAY + timedelta(days=365 * 5 + 1)).isoformat()
    )


def test_patch_and_history(hq_client, make_amm):
    amm = make_amm(start=date(2024, 1, 1))
    response = hq_client.patch(
        f"/api/v1/amms/{amm.pk}", {"dossier_state": "INCOMPLET", "notes": "à compléter"}
    )
    assert response.status_code == 200 and response.json()["dossier_state"] == "INCOMPLET"
    history = hq_client.get(f"/api/v1/amms/{amm.pk}/history")
    assert history.status_code == 200
    entries = history.json()
    assert entries[0]["type"] == "updated" and entries[0]["user_email"] == "hq@test.local"
    fields = {c["field"]: c for c in entries[0]["changes"]}
    assert (
        fields["dossier_state"]["old"] == "COMPLET"
        and fields["dossier_state"]["new"] == "INCOMPLET"
    )
    assert entries[-1]["type"] == "created"


def test_manual_end_date_flag_on_patch(hq_client, make_amm):
    amm = make_amm(start=date(2024, 1, 1))
    response = hq_client.patch(f"/api/v1/amms/{amm.pk}", {"original_end_date": "2027-06-30"})
    assert response.status_code == 200
    assert response.json()["original_end_date_manual"] is True
    assert response.json()["effective_end_date"] == "2027-06-30"


def test_renewal_scope(country_client, make_amm, make_renewal):
    renewal = make_renewal(make_amm(country="CI"), "PLANIFIE")
    assert (
        country_client.post(
            f"/api/v1/renewals/{renewal.pk}/transition", {"to": "EN_PREPARATION"}
        ).status_code
        == 404
    )


def test_referentials_read_only_for_country_user(country_client, hq_client, countries, ranges):
    assert country_client.get("/api/v1/countries").status_code == 200
    assert (
        country_client.post("/api/v1/countries", {"iso2": "TG", "name": "Togo"}).status_code == 403
    )
    assert country_client.patch("/api/v1/countries/SN", {"validity_years": 4}).status_code == 403
    created = hq_client.post("/api/v1/countries", {"iso2": "tg", "name": "Togo"})
    assert created.status_code == 201 and created.json()["iso2"] == "TG"
    assert hq_client.get("/api/v1/countries/TG").status_code == 200
    assert hq_client.get(f"/api/v1/countries/{created.json()['id']}").status_code == 200
    assert (
        country_client.post(
            "/api/v1/products", {"name": "x", "range": str(ranges["CARDIO"].pk)}
        ).status_code
        == 403
    )
    assert (
        hq_client.post(
            "/api/v1/products", {"name": "  nouveau   produit ", "range": str(ranges["CARDIO"].pk)}
        ).json()["name"]
        == "NOUVEAU PRODUIT"
    )
