"""1.2.1 : classeurs en lecture seule hors CEO et siège ; pages « à imprimer » dans le bilan."""

import pytest

from apps.binders.models import BinderPrintMark

pytestmark = pytest.mark.django_db


@pytest.fixture
def amm(make_amm):
    return make_amm(country="SN")


def _page(body, amm):
    return next(p for s in body["sections"] for p in s["pages"] if p["amm_id"] == str(amm.pk))


def _binder(client, amm):
    return client.get(f"/api/v1/binders/locate?amm={amm.pk}").json()["binder_key"]


def test_country_reads_but_cannot_change_a_binder(country_client, amm):
    key = _binder(country_client, amm)
    assert country_client.get(f"/api/v1/binders/{key}").status_code == 200
    writes = [
        (f"/api/v1/binders/{key}/check", {"amm": str(amm.pk), "result": "CONFORME"}),
        (f"/api/v1/binders/{key}/pages/{amm.pk}/print", {"to_print": True}),
        (f"/api/v1/binders/{key}/pages", {"product_name": "NOUVEAU 10MG CP B30"}),
    ]
    for url, data in writes:
        response = country_client.post(url, data, format="json")
        assert response.status_code == 403, url
        assert "lecture seule" in response.json()["detail"]
    # Signaler qu'on a le classeur ouvert reste permis.
    assert country_client.post(f"/api/v1/binders/{key}/presence").status_code == 204


def test_hq_marks_a_page_to_print_without_changing_conformity(hq_client, amm):
    key = _binder(hq_client, amm)
    before = _page(hq_client.get(f"/api/v1/binders/{key}").json(), amm)
    body = hq_client.post(
        f"/api/v1/binders/{key}/pages/{amm.pk}/print", {"to_print": True}, format="json"
    ).json()
    page = _page(body, amm)
    assert page["to_print"] is True and body["to_print"] == 1
    assert page["conformity"] == before["conformity"]
    # Bilan de l'étagère : le même compte.
    shelf = {b["key"]: b for b in hq_client.get("/api/v1/binders").json()}
    assert shelf[key]["to_print"] == 1
    # Imprimée et rangée : l'état change, rien n'est supprimé.
    body = hq_client.post(
        f"/api/v1/binders/{key}/pages/{amm.pk}/print", {"to_print": False}, format="json"
    ).json()
    assert _page(body, amm)["to_print"] is False and body["to_print"] == 0
    mark = BinderPrintMark.objects.get(amm=amm)
    assert mark.to_print is False and mark.history.count() == 2


def test_conforme_page_can_still_be_to_print(hq_client, amm):
    key = _binder(hq_client, amm)
    hq_client.post(f"/api/v1/binders/{key}/pages/{amm.pk}/print", {"to_print": True}, format="json")
    body = hq_client.post(
        f"/api/v1/binders/{key}/check", {"amm": str(amm.pk), "result": "CONFORME"}, format="json"
    ).json()
    page = _page(body, amm)
    assert page["to_print"] is True and page["check"]["result"] == "CONFORME"
