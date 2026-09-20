"""Intégration PostgreSQL + Redis réel pour GET /api/v1/health.

Contrairement à `test_health_version_badge.py` (SQLite, Redis simulé par `monkeypatch`), ce module
tourne sur la base PostgreSQL de CI et le vrai service Redis du docker-compose : il vérifie que le
ping Redis aboutit réellement (`redis: true`) et que le schéma OpenAPI reste typé une fois généré
sur ce backend PostgreSQL. Ne modifie jamais le code testé (T1/T2 hors scope).
"""

import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_ok_with_real_postgres_and_redis(settings):
    """Base PostgreSQL et Redis réels disponibles : 200, `redis` vrai à true, 4 clés exactes."""
    client = APIClient()
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "database", "redis", "version"}
    assert body["status"] == "ok"
    assert body["database"] is True
    # Ping réel contre le service `redis` du docker-compose : pas de simulation ici.
    assert body["redis"] is True
    assert body["version"] == settings.APP_VERSION


def test_health_exposes_configured_version_on_postgres(settings):
    """`APP_VERSION` normalisée par les settings, exposée telle quelle même sur PostgreSQL."""
    settings.APP_VERSION = "1.4.2-rc.1+sha.abc1234"
    client = APIClient()
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["version"] == "1.4.2-rc.1+sha.abc1234"


def test_health_schema_is_typed_on_postgres():
    """Schéma drf-spectacular généré sur ce backend PostgreSQL : mêmes garanties que CA6 (T1)."""
    generator = SchemaGenerator()
    schema = generator.get_schema(request=None, public=True)

    health_get = schema["paths"]["/api/v1/health/"]["get"]
    for code in ("200", "503"):
        ref = health_get["responses"][code]["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/Health"

    health_schema = schema["components"]["schemas"]["Health"]
    assert set(health_schema["required"]) == {"status", "database", "redis", "version"}
    assert health_schema["properties"]["status"]["$ref"] == "#/components/schemas/HealthStatusEnum"

    enum_schema = schema["components"]["schemas"]["HealthStatusEnum"]
    assert set(enum_schema["enum"]) == {"ok", "degraded"}
