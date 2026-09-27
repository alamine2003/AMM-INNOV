"""Classeurs d'archivage : ordre des pages, cloisonnement par pays, constat, PDF du siège."""

from datetime import date

import pytest

from apps.amm.models import MarketingAuthorization, Renewal
from apps.binders.layout import binders_of, sort_name
from apps.binders.models import BinderCheck
from apps.catalog.models import Product
from apps.imports.models import DossierImport, DossierReviewPoint

pytestmark = pytest.mark.django_db


@pytest.fixture
def shelf_data(make_amm, ranges, countries):
    def amm(name, range_code, country="SN", **kwargs):
        product, _ = Product.objects.get_or_create(
            name=name, defaults={"range": ranges[range_code] if range_code else None}
        )
        return make_amm(country=country, product_obj=product, **kwargs)

    return {
        # Créées dans le désordre, comme les lignes ajoutées plus tard dans l'Excel.
        "gripex": amm("GRIPEX CP B20", "GENERALE"),
        "acarbose": amm("ACARBOSE GH 100MG", "GENERALE"),
        "litacold": amm("LITACOLD CPR B/80", "GENERALE"),
        "amlo": amm("AMLODIPINE GH 5MG", "CARDIO"),
        "vita": amm("VITAGEN SIROP", "BIEN_ETRE"),
        "ml_cardio": amm("AMLODIPINE GH 5MG", "CARDIO", country="ML"),
        "ml_gen": amm("ZINCGEN 20MG", "GENERALE", country="ML"),
        "ml_aaa": amm("ÉPIGEN 10MG", "GENERALE", country="ML"),
        "ci": amm("ARTEGEN CI", "GENERALE", country="CI"),
    }


def test_headquarters_has_four_binders_and_others_one(countries):
    assert [b.key for b in binders_of(countries["SN"])] == [
        "SN-generale-a-k",
        "SN-generale-l-z",
        "SN-cardio",
        "SN-bien-etre",
    ]
    assert [b.key for b in binders_of(countries["ML"])] == ["ML"]


def test_pages_follow_the_paper_order(hq_client, shelf_data):
    body = hq_client.get("/api/v1/binders/SN-generale-a-k").json()
    names = [p["product_name"] for s in body["sections"] for p in s["pages"]]
    assert names == ["ACARBOSE GH 100MG", "GRIPEX CP B20"]
    assert hq_client.get("/api/v1/binders/SN-generale-l-z").json()["total"] == 1

    mali = hq_client.get("/api/v1/binders/ML").json()
    # Pas de Bien-être au Mali dans ces données : pas d'intercalaire vide.
    assert [s["code"] for s in mali["sections"]] == ["GENERALE", "CARDIO"]
    generale = mali["sections"][0]["pages"]
    # Tri sans accents : ÉPIGEN avant ZINCGEN ; numérotation continue du classeur.
    assert [sort_name(p["product_name"]) for p in generale] == ["EPIGEN 10MG", "ZINCGEN 20MG"]
    assert [p["page"] for s in mali["sections"] for p in s["pages"]] == [1, 2, 3]
    assert mali["sections"][1]["pages"][0]["section_page"] == 1


def test_country_sees_only_its_binders(hq_client, country_client, shelf_data):
    mine = {b["key"] for b in country_client.get("/api/v1/binders").json()}
    assert mine == {"SN-generale-a-k", "SN-generale-l-z", "SN-cardio", "SN-bien-etre", "ML"}
    everything = [b["key"] for b in hq_client.get("/api/v1/binders").json()]
    assert everything[0] == "SN-generale-a-k" and "CI" in everything
    assert country_client.get("/api/v1/binders/CI").status_code == 404
    response = country_client.post(
        "/api/v1/binders/CI/check",
        {"amm": str(shelf_data["ci"].pk), "result": "CONFORME"},
        format="json",
    )
    assert response.status_code == 404


def test_conforme_then_absent_then_undo(country_client, shelf_data):
    amm = shelf_data["amlo"]
    url = "/api/v1/binders/SN-cardio"
    body = country_client.post(
        f"{url}/check", {"amm": str(amm.pk), "result": "CONFORME"}, format="json"
    ).json()
    page = body["sections"][0]["pages"][0]
    assert page["check"]["result"] == "CONFORME" and page["check"]["checked_by"] == "Fatou"
    # Papier présent, décision sans scan : à scanner.
    assert page["to_scan"] is True and body["to_scan"] == 1 and body["checked"] == 1

    body = country_client.post(
        f"{url}/check", {"amm": str(amm.pk), "result": "ABSENT"}, format="json"
    ).json()
    assert body["absent"] == 1 and body["to_scan"] == 0

    body = country_client.post(f"{url}/uncheck", {"amm": str(amm.pk)}, format="json").json()
    assert body["checked"] == 0 and not BinderCheck.objects.exists()


def test_page_outside_the_binder_is_refused(country_client, shelf_data):
    response = country_client.post(
        "/api/v1/binders/SN-cardio/check",
        {"amm": str(shelf_data["gripex"].pk), "result": "CONFORME"},
        format="json",
    )
    assert response.status_code == 403


def test_paper_value_corrects_the_record_and_closes_the_gap(users, country_client, shelf_data):
    amm = shelf_data["amlo"]
    amm.original_start_date = date(2010, 12, 22)
    amm.save()
    batch = DossierImport.objects.create(root_name="X", created_by=users["hq"])
    point = DossierReviewPoint.objects.create(
        batch=batch,
        amm=amm,
        code="value_mismatch",
        field="original_start_date",
        recorded_value="2010-12-22",
        scan_value="2015-12-22",
        message="Date de début : la fiche indique 22/12/2010, le scan indique 22/12/2015.",
        fingerprint="x",
    )
    page = country_client.get("/api/v1/binders/SN-cardio").json()["sections"][0]["pages"][0]
    assert page["discrepancies"][0]["slot"] == "original"
    assert page["discrepancies"][0]["field"] == "start_date"

    body = country_client.post(
        "/api/v1/binders/SN-cardio/check",
        {
            "amm": str(amm.pk),
            "result": "CORRIGE",
            "corrections": [
                {"slot": "original", "field": "start_date", "value": "2015-12-22"},
                {"slot": "renewal", "field": "number", "value": "AMM/SN/2020/0042"},
                {"slot": "renewal", "field": "start_date", "value": "2020-12-22"},
            ],
        },
        format="json",
    ).json()
    page = body["sections"][0]["pages"][0]
    assert page["check"]["result"] == "CORRIGE" and len(page["check"]["corrections"]) == 3
    assert page["discrepancies"] == []
    amm.refresh_from_db()
    assert amm.original_start_date == date(2015, 12, 22)
    # Renouvellement vu sur le papier mais inconnu : créé, obtenu.
    renewal = Renewal.objects.get(amm=amm)
    assert renewal.workflow_status == "OBTENU" and renewal.number == "AMM/SN/2020/0042"
    assert page["renewal"]["number"] == "AMM/SN/2020/0042"
    point.refresh_from_db()
    assert point.status == DossierReviewPoint.Status.APPLIED
    assert point.resolved_by == users["country"]
    history = amm.history.filter(history_change_reason="Vérifié sur le classeur papier")
    assert history.exists() and history.first().history_user == users["country"]


def test_end_before_start_is_refused(country_client, shelf_data):
    amm = shelf_data["amlo"]
    response = country_client.post(
        "/api/v1/binders/SN-cardio/check",
        {
            "amm": str(amm.pk),
            "result": "CORRIGE",
            "corrections": [{"slot": "original", "field": "end_date", "value": "2000-01-01"}],
        },
        format="json",
    )
    assert response.status_code == 400
    assert not BinderCheck.objects.exists()
    assert MarketingAuthorization.objects.get(pk=amm.pk).original_end_date != date(2000, 1, 1)


def test_extra_pages(country_client, shelf_data):
    response = country_client.post(
        "/api/v1/binders/ML/extras", {"product_name": " pharmagen   sirop "}, format="json"
    )
    assert response.status_code == 201 and response.json()["product_name"] == "PHARMAGEN SIROP"
    body = country_client.get("/api/v1/binders/ML").json()
    assert body["extras"] == 1 and body["extra_pages"][0]["product_name"] == "PHARMAGEN SIROP"
    extra = body["extra_pages"][0]["id"]
    assert country_client.delete(f"/api/v1/binders/ML/extras/{extra}").status_code == 204
    assert country_client.get("/api/v1/binders/ML").json()["extras"] == 0


def test_pdf_is_for_headquarters_only(hq_client, country_client, shelf_data):
    country_client.post(
        "/api/v1/binders/ML/check",
        {"amm": str(shelf_data["ml_gen"].pk), "result": "CONFORME"},
        format="json",
    )
    response = hq_client.get("/api/v1/binders/ML/pdf")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert "Classeur_ML_" in response["Content-Disposition"]
    assert country_client.get("/api/v1/binders/ML/pdf").status_code == 403
