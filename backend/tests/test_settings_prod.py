"""Settings de production : hôte Render accepté automatiquement."""

import importlib
import os

import pytest


@pytest.fixture
def prod_settings(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "x" * 50)
    monkeypatch.setenv("ALLOWED_HOSTS", "api.amm-innov.com")
    monkeypatch.setenv("CSRF_TRUSTED_ORIGINS", "https://api.amm-innov.com")

    def load():
        # `prod` fait `from .base import *` : recharger base d'abord pour relire l'environnement.
        import config.settings.base as base
        import config.settings.prod as prod

        importlib.reload(base)
        return importlib.reload(prod)

    return load


def test_railway_domains_are_allowed(prod_settings, monkeypatch):
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "amm-innov-backend-production.up.railway.app")
    monkeypatch.setenv("RAILWAY_PRIVATE_DOMAIN", "amm-innov-backend.railway.internal")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env-1")
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    prod = prod_settings()
    assert prod.ALLOWED_HOSTS == [
        "api.amm-innov.com",
        "amm-innov-backend-production.up.railway.app",
        "amm-innov-backend.railway.internal",
        "healthcheck.railway.app",
    ]
    assert "https://amm-innov-backend-production.up.railway.app" in prod.CSRF_TRUSTED_ORIGINS
    assert prod.REST_FRAMEWORK["NUM_PROXIES"] == 1


def test_without_platform_hostname(prod_settings, monkeypatch):
    for name in (
        "RAILWAY_PUBLIC_DOMAIN",
        "RAILWAY_PRIVATE_DOMAIN",
        "RAILWAY_ENVIRONMENT_ID",
        "RENDER_EXTERNAL_HOSTNAME",
    ):
        monkeypatch.delenv(name, raising=False)
    prod = prod_settings()
    assert prod.ALLOWED_HOSTS == ["api.amm-innov.com"]
    assert "RAILWAY_PUBLIC_DOMAIN" not in os.environ


def test_r2_variables_pasted_with_a_trailing_newline_still_work(prod_settings, monkeypatch):
    # Valeurs collées dans le tableau de bord Render avec un retour à la ligne final : boto3
    # refusait « https://….r2.cloudflarestorage.com\n » (500 à l'envoi des scans).
    monkeypatch.setenv("DOCUMENT_STORAGE", "s3\n")
    monkeypatch.setenv("S3_ENDPOINT_URL", "https://compte.r2.cloudflarestorage.com\n")
    monkeypatch.setenv("S3_BUCKET", " amm-documents ")
    monkeypatch.setenv("S3_ACCESS_KEY", "cle\n")
    monkeypatch.setenv("S3_SECRET_KEY", "secret\n")
    prod = prod_settings()
    options = prod.STORAGES["default"]["OPTIONS"]
    assert options["endpoint_url"] == "https://compte.r2.cloudflarestorage.com"
    assert (options["bucket_name"], options["access_key"], options["secret_key"]) == (
        "amm-documents",
        "cle",
        "secret",
    )
