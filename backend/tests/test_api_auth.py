import pytest

pytestmark = pytest.mark.django_db


def test_login_refresh_me_logout(anon_client, users):
    response = anon_client.post(
        "/api/v1/auth/login", {"email": "sn@test.local", "password": "Passw0rd!"}
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"access", "refresh", "user"}
    assert body["user"]["email"] == "sn@test.local"
    assert body["user"]["role"] == "COUNTRY_REGULATORY"
    assert sorted(body["user"]["countries"]) == ["ML", "SN"]

    refreshed = anon_client.post("/api/v1/auth/refresh", {"refresh": body["refresh"]})
    assert refreshed.status_code == 200 and "access" in refreshed.json()

    anon_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed.json()['access']}")
    me = anon_client.get("/api/v1/me")
    assert me.status_code == 200 and me.json()["first_name"] == "Fatou"

    new_refresh = refreshed.json().get("refresh", body["refresh"])
    logout = anon_client.post("/api/v1/auth/logout", {"refresh": new_refresh})
    assert logout.status_code == 204
    assert anon_client.post("/api/v1/auth/refresh", {"refresh": new_refresh}).status_code == 401


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
