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
    monkeypatch.delenv("RENDER_EXTERNAL_HOSTNAME", raising=False)
    prod = prod_settings()
    assert prod.ALLOWED_HOSTS == [
        "api.amm-innov.com",
        "amm-innov-backend-production.up.railway.app",
        "amm-innov-backend.railway.internal",
    ]
    assert "https://amm-innov-backend-production.up.railway.app" in prod.CSRF_TRUSTED_ORIGINS
    assert prod.REST_FRAMEWORK["NUM_PROXIES"] == 1


def test_without_platform_hostname(prod_settings, monkeypatch):
    for name in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_PRIVATE_DOMAIN", "RENDER_EXTERNAL_HOSTNAME"):
        monkeypatch.delenv(name, raising=False)
    prod = prod_settings()
    assert prod.ALLOWED_HOSTS == ["api.amm-innov.com"]
    assert "RAILWAY_PUBLIC_DOMAIN" not in os.environ
