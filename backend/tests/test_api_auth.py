import pytest

pytestmark = pytest.mark.django_db


def test_login_refresh_me_logout(anon_client, users):
    response = anon_client.post(
        "/api/v1/auth/login", {"email": "sn@test.local", "password": "Passw0rd!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access", "user"}  # le refresh ne transite que par le cookie httpOnly
    assert body["user"]["email"] == "sn@test.local"
    assert body["user"]["role"] == "COUNTRY_REGULATORY"
    assert sorted(body["user"]["countries"]) == ["ML", "SN"]
    cookie = response.cookies["amm_refresh"]
    assert cookie["httponly"] and cookie["path"] == "/api/v1/auth" and cookie["samesite"] == "Lax"
    first_refresh = cookie.value

    # le client garde le cookie : le rafraîchissement ne demande aucun corps
    refreshed = anon_client.post("/api/v1/auth/refresh", {})
    assert refreshed.status_code == 200 and "access" in refreshed.json()
    assert "refresh" not in refreshed.json()
    rotated = refreshed.cookies["amm_refresh"].value
    assert rotated and rotated != first_refresh
    # l'ancien refresh est révoqué (rotation + liste noire)
    assert anon_client.post("/api/v1/auth/refresh", {"refresh": first_refresh}).status_code == 401

    anon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.json()['access']}")
    me = anon_client.get("/api/v1/me")
    assert me.status_code == 200 and me.json()["first_name"] == "Fatou"

    logout = anon_client.post("/api/v1/auth/logout", {})
    assert logout.status_code == 204
    assert logout.cookies["amm_refresh"].value == ""  # cookie effacé
    anon_client.credentials()
    assert anon_client.post("/api/v1/auth/refresh", {"refresh": rotated}).status_code == 401


def test_refresh_rejects_foreign_origin(anon_client, users):
    anon_client.post("/api/v1/auth/login", {"email": "sn@test.local", "password": "Passw0rd!"})
    forbidden = anon_client.post("/api/v1/auth/refresh", {}, HTTP_ORIGIN="https://evil.example")
    assert forbidden.status_code == 403
    allowed = anon_client.post("/api/v1/auth/refresh", {}, HTTP_ORIGIN="http://localhost:5173")
    assert allowed.status_code == 200


def test_refresh_without_cookie_is_401(anon_client, db):
    assert anon_client.post("/api/v1/auth/refresh", {}).status_code == 401


def test_login_wrong_password(anon_client, users):
    response = anon_client.post(
        "/api/v1/auth/login", {"email": "sn@test.local", "password": "nope"}
    )
    assert response.status_code == 401


def test_anonymous_is_rejected(anon_client, db):
    assert anon_client.get("/api/v1/amms").status_code == 401
    assert anon_client.get("/api/v1/me").status_code == 401


def test_health_is_public(anon_client, db):
    response = anon_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["database"] is True and isinstance(body["redis"], bool)


def test_openapi_schema_and_docs(anon_client, hq_client):
    # Documentation réservée aux utilisateurs connectés (session admin ou JWT).
    assert anon_client.get("/api/schema/").status_code == 403
    assert hq_client.get("/api/schema/").status_code == 200
    assert hq_client.get("/api/docs/").status_code == 200
