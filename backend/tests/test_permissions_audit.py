"""1.2.3 : permissions réglables par le CEO, audit et traçabilité."""

import secrets
from datetime import date

import pytest

from apps.accounts.models import ActionGrant, User
from apps.accounts.roles import Action, can
from apps.catalog.models import Product
from apps.core.models import TrashEntry

pytestmark = pytest.mark.django_db


def _cell(matrix, action, role):
    row = next(item for item in matrix["actions"] if item["action"] == action)
    return row["roles"][role]


# --- Permissions ----------------------------------------------------------------------------


def test_only_the_ceo_sees_and_sets_permissions(ceo_client, hq_client, country_client):
    assert hq_client.get("/api/v1/permissions").status_code == 403
    assert country_client.get("/api/v1/permissions").status_code == 403
    matrix = ceo_client.get("/api/v1/permissions").json()
    assert {action["action"] for action in matrix["actions"]} == {a.value for a in Action}
    assert _cell(matrix, "catalog.manage", "HQ_REGULATORY") is True
    assert _cell(matrix, "catalog.manage", "COUNTRY_REGULATORY") is False
    editable = {role["value"]: role["editable"] for role in matrix["roles"]}
    assert editable == {
        "CEO_ADMIN": False,
        "HQ_REGULATORY": True,
        "COUNTRY_REGULATORY": True,
    }


def test_granting_an_action_opens_the_api_to_the_role(ceo_client, country_client):
    created = {"iso2": "BF", "name": "Burkina Faso"}
    assert country_client.post("/api/v1/countries", created).status_code == 403
    response = ceo_client.put(
        "/api/v1/permissions",
        {"grants": [{"action": "catalog.manage", "role": "COUNTRY_REGULATORY", "allowed": True}]},
        format="json",
    )
    assert response.status_code == 200
    assert _cell(response.json(), "catalog.manage", "COUNTRY_REGULATORY") is True
    assert country_client.post("/api/v1/countries", created).status_code == 201
    me = country_client.get("/api/v1/me").json()
    assert "catalog.manage" in me["actions"]


def test_withdrawing_an_action_closes_it_with_a_clear_message(ceo_client, hq_client, product):
    ceo_client.put(
        "/api/v1/permissions",
        {"grants": [{"action": "catalog.manage", "role": "HQ_REGULATORY", "allowed": False}]},
        format="json",
    )
    response = hq_client.patch(f"/api/v1/products/{product.pk}", {"name": "X"}, format="json")
    assert response.status_code == 403
    assert response.json()["detail"] == "Vous ne pouvez pas modifier les référentiels."
    grant = ActionGrant.objects.get(action="catalog.manage", role="HQ_REGULATORY")
    assert grant.history.first().history_user.role == User.Role.CEO_ADMIN


def test_nobody_can_lock_the_ceo_out(ceo_client, users):
    for grant in (
        {"action": "permissions.manage", "role": "HQ_REGULATORY", "allowed": True},
        {"action": "catalog.manage", "role": "CEO_ADMIN", "allowed": False},
        {"action": "nope", "role": "HQ_REGULATORY", "allowed": True},
    ):
        response = ceo_client.put("/api/v1/permissions", {"grants": [grant]}, format="json")
        assert response.status_code == 400
    assert not ActionGrant.objects.exists()
    assert all(can(users["ceo"], action) for action in Action)


def test_unchanged_cells_are_not_stored(ceo_client):
    ceo_client.put(
        "/api/v1/permissions",
        {"grants": [{"action": "audit.view", "role": "HQ_REGULATORY", "allowed": True}]},
        format="json",
    )
    assert not ActionGrant.objects.exists()


def test_trash_granted_to_a_country_role_shows_its_countries_only(
    ceo_client, country_client, make_amm
):
    ceo_client.put(
        "/api/v1/permissions",
        {"grants": [{"action": "trash.restore", "role": "COUNTRY_REGULATORY", "allowed": True}]},
        format="json",
    )
    TrashEntry.objects.create(
        label="SN", kind="AMM", model="amm.X", object_id="1", country="SN", payload={}
    )
    TrashEntry.objects.create(
        label="CI", kind="AMM", model="amm.X", object_id="2", country="CI", payload={}
    )
    listed = country_client.get("/api/v1/trash").json()["results"]
    assert [row["label"] for row in listed] == ["SN"]


# --- Audit ----------------------------------------------------------------------------------


def test_audit_is_for_hq_and_ceo_by_default(country_client, hq_client):
    assert country_client.get("/api/v1/audit").status_code == 403
    assert hq_client.get("/api/v1/audit").status_code == 200
    filters = hq_client.get("/api/v1/audit/filters").json()
    assert {"amm.MarketingAuthorization", "accounts.User"} <= {t["value"] for t in filters["types"]}


def test_audit_tells_who_did_what(ceo_client, hq_client, users, make_amm):
    alone = Product.objects.create(name="SEUL GH 1MG CP B10")
    amm = make_amm(original_start_date=date(2015, 1, 1))
    hq_client.patch(f"/api/v1/amms/{amm.pk}", {"notes": "Vu au classeur"}, format="json")
    hq_client.delete(f"/api/v1/products/{alone.pk}")
    entry = TrashEntry.objects.get(object_id=str(alone.pk))
    ceo_client.post(f"/api/v1/trash/{entry.pk}/restore")

    events = ceo_client.get("/api/v1/audit").json()["results"]
    actions = [(event["action"], event["model"]) for event in events]
    assert actions[:3] == [
        ("restored", "catalog.Product"),
        ("deleted", "catalog.Product"),
        ("updated", "amm.MarketingAuthorization"),
    ]
    assert events[0]["user"] == users["ceo"].full_name
    update = events[2]
    assert update["user"] == users["hq"].full_name and update["country"] == "SN"
    assert {"old": None, "new": "Vu au classeur"} in [
        {"old": change["old"], "new": change["new"]} for change in update["changes"]
    ]


def test_audit_filters_by_person_type_action_and_country(ceo_client, hq_client, users, make_amm):
    sn = make_amm(country="SN")
    ml = make_amm(country="ML")
    hq_client.patch(f"/api/v1/amms/{sn.pk}", {"notes": "SN"}, format="json")
    hq_client.patch(f"/api/v1/amms/{ml.pk}", {"notes": "ML"}, format="json")
    query = (
        f"/api/v1/audit?user={users['hq'].pk}&model=amm.MarketingAuthorization"
        "&action=updated&country=ML"
    )
    body = ceo_client.get(query).json()
    assert body["count"] == 1 and body["results"][0]["object_id"] == str(ml.pk)
    assert ceo_client.get("/api/v1/audit?since=2999-01-01").json()["count"] == 0
    assert ceo_client.get("/api/v1/audit?since=hier").status_code == 400
    assert ceo_client.get("/api/v1/audit?user=personne").status_code == 400


def test_audit_granted_to_a_country_role_shows_its_countries_only(
    ceo_client, country_client, hq_client, make_amm
):
    ceo_client.put(
        "/api/v1/permissions",
        {"grants": [{"action": "audit.view", "role": "COUNTRY_REGULATORY", "allowed": True}]},
        format="json",
    )
    sn = make_amm(country="SN")
    ci = make_amm(country="CI")
    hq_client.patch(f"/api/v1/amms/{sn.pk}", {"notes": "SN"}, format="json")
    hq_client.patch(f"/api/v1/amms/{ci.pk}", {"notes": "CI"}, format="json")
    countries = {
        event["country"] for event in country_client.get("/api/v1/audit").json()["results"]
    }
    assert "SN" in countries and "CI" not in countries  # ses pays : SN et ML


def test_logins_and_account_changes_are_traced(client, ceo_client, users):
    # Mot de passe tiré au hasard : aucun identifiant écrit dans le dépôt.
    secret = secrets.token_urlsafe(16)
    users["hq"].set_password(secret)
    users["hq"].save()
    response = client.post(
        "/api/v1/auth/login",
        {"email": "hq@test.local", "password": secret},
        content_type="application/json",
    )
    assert response.status_code == 200
    logins = ceo_client.get(f"/api/v1/audit?action=login&user={users['hq'].pk}").json()
    assert [event["label"] for event in logins["results"]] == ["hq@test.local"]
    assert logins["results"][0]["user"] == users["hq"].full_name
    ceo_client.patch(f"/api/v1/users/{users['country'].pk}", {"last_name": "Diop"}, format="json")
    changes = ceo_client.get("/api/v1/audit?model=accounts.User&action=updated").json()
    assert changes["results"][0]["user"] == users["ceo"].full_name
    # Le mot de passe n'est jamais copié dans l'historique.
    history_fields = {f.name for f in users["hq"].history.model._meta.fields}
    assert "password" not in history_fields


def test_audit_pages(ceo_client, hq_client, make_amm):
    amm = make_amm()
    for index in range(55):
        hq_client.patch(f"/api/v1/amms/{amm.pk}", {"notes": str(index)}, format="json")
    first = ceo_client.get("/api/v1/audit?action=updated").json()
    second = ceo_client.get("/api/v1/audit?action=updated&page=2").json()
    assert first["count"] >= 55 and first["pages"] == 2
    assert len(first["results"]) == 50
    assert not {e["id"] for e in first["results"]} & {e["id"] for e in second["results"]}
