"""1.3.1 : langue de l'interface, choisie par l'utilisateur et gardée sur son compte."""

import pytest

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_language_is_french_by_default_and_returned_with_the_account(country_client, users):
    assert users["country"].language == "fr"
    assert country_client.get("/api/v1/me").json()["language"] == "fr"


def test_user_switches_own_language(country_client, users):
    response = country_client.patch("/api/v1/me", {"language": "en"}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "en" and body["email"] == users["country"].email
    assert "actions" in body  # même forme que GET /me : l'interface remplace son utilisateur
    users["country"].refresh_from_db()
    assert users["country"].language == "en"
    record = users["country"].history.first()
    assert record.language == "en" and record.history_change_reason == "Langue de l'interface"


def test_me_update_changes_nothing_but_the_language(country_client, users):
    user = users["country"]
    before = (user.role, user.is_active, user.email, sorted(c.iso2 for c in user.countries.all()))
    response = country_client.patch(
        "/api/v1/me",
        {
            "language": "en",
            "role": "CEO_ADMIN",
            "is_active": False,
            "email": "x@y.z",
            "countries": [],
        },
        format="json",
    )
    assert response.status_code == 200
    user.refresh_from_db()
    after = (user.role, user.is_active, user.email, sorted(c.iso2 for c in user.countries.all()))
    assert after == before and user.language == "en"


def test_unknown_language_is_refused(country_client, users):
    response = country_client.patch("/api/v1/me", {"language": "de"}, format="json")
    assert response.status_code == 400
    users["country"].refresh_from_db()
    assert users["country"].language == "fr"


def test_anonymous_cannot_set_a_language(anon_client):
    assert anon_client.patch("/api/v1/me", {"language": "en"}, format="json").status_code == 401


def test_login_answer_carries_the_language(users):
    """La connexion renvoie le compte tel que /me (MeSerializer) : la langue y figure."""
    from apps.accounts.serializers import MeSerializer

    User.objects.filter(pk=users["hq"].pk).update(language="en")
    users["hq"].refresh_from_db()
    assert MeSerializer(users["hq"]).data["language"] == "en"


def test_admin_sets_the_language_of_an_account(ceo_client, users):
    response = ceo_client.patch(
        f"/api/v1/users/{users['hq'].pk}", {"language": "en"}, format="json"
    )
    assert response.status_code == 200 and response.json()["language"] == "en"


def test_database_keeps_the_default_for_older_code(users):
    """Retour arrière : un compte inséré sans la colonne (code d'avant) reçoit « fr »."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "select column_default from information_schema.columns "
            "where table_name = 'accounts_user' and column_name = 'language'"
        )
        assert "fr" in (cursor.fetchone()[0] or "")
