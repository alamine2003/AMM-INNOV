"""Surveillance Sentry : inactive sans DSN, et sans donnée personnelle quand elle est active."""

import pytest

from config import sentry


def test_no_dsn_means_no_monitoring():
    """Sans SENTRY_DSN, rien n'est initialisé : l'application tourne telle quelle."""
    assert sentry.sentry_options("", environment="production") is None
    assert sentry.init_sentry(None, environment="production") is False


def test_options_never_carry_personal_data():
    options = sentry.sentry_options(
        "https://clef@o0.ingest.sentry.io/1", environment="production", release="1.2.3"
    )
    assert options["send_default_pii"] is False
    # Un scan d'AMM ou une fiche ne doit jamais partir chez un tiers.
    assert options["max_request_body_size"] == "never"
    assert options["environment"] == "production" and options["release"] == "1.2.3"


@pytest.mark.parametrize(
    "path,expected", [("/api/v1/health", 0.0), ("/metrics", 0.0), ("/api/v1/amms", 0.25)]
)
def test_health_and_metrics_are_not_traced(path, expected):
    """Sondes et métriques sont interrogées en continu : elles noieraient les traces."""
    options = sentry.sentry_options(
        "https://clef@o0.ingest.sentry.io/1", environment="production", traces_sample_rate=0.25
    )
    assert options["traces_sampler"]({"asgi_scope": {"path": path}}) == expected


def test_binding_without_sentry_is_a_no_op():
    """Sans surveillance active, marquer une requête ou une tâche ne doit rien coûter ni lever."""
    assert sentry.is_active() is False
    sentry.bind_request("abc123", user_id="42")
    sentry.bind_task("apps.core.tasks.recover_pending_work", "abc123")


def test_missing_package_never_blocks_startup(monkeypatch, caplog):
    """SENTRY_DSN défini sur une image sans sentry-sdk : l'application démarre quand même."""
    import builtins

    real_import = builtins.__import__

    def refuse_sentry(name, *args, **kwargs):
        if name.startswith("sentry_sdk"):
            raise ImportError("paquet absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_sentry)
    dsn = "https://clef@o0.ingest.sentry.io/1"
    assert sentry.init_sentry(dsn, environment="production") is False
    assert "surveillance inactive" in caplog.text
