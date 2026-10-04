"""Numéro de version : fichier VERSION lu par l'API, règle de passage de docs/versionnement.md."""

import importlib.util
from pathlib import Path

import pytest
from django.conf import settings

from config.settings.base import clean_app_version, read_version_file

ROOT = Path(settings.BASE_DIR).parent
spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_health_shows_the_published_version(client, monkeypatch):
    published = (Path(settings.BASE_DIR) / "VERSION").read_text().strip()
    assert release.SEMVER.match(published)
    assert clean_app_version(read_version_file(Path(settings.BASE_DIR) / "VERSION")) == published
    monkeypatch.setattr(settings, "APP_VERSION", published)
    assert client.get("/api/v1/health").json()["version"] == published


def test_missing_version_file_falls_back_to_dev(tmp_path):
    assert clean_app_version(read_version_file(tmp_path / "VERSION")) == "dev"


@pytest.mark.parametrize(
    ("version", "expected", "kind"),
    [
        ("1.0.0", "1.0.1", "mise à jour corrective"),
        ("1.0.8", "1.0.9", "mise à jour corrective"),
        ("1.0.9", "1.1.0", "palier"),
        ("1.1.0", "1.1.1", "mise à jour corrective"),
        ("1.8.9", "1.9.0", "palier"),
        ("1.9.9", "2.0.0", "version majeure"),
    ],
)
def test_next_version_follows_the_plan(version, expected, kind):
    assert release.following(version) == expected
    assert release.kind(expected) == kind


@pytest.mark.parametrize("version", ["1.0", "1.0.10", "1.10.0", "v1.0.1", "1.0.1-rc1"])
def test_versions_outside_the_plan_are_refused(version):
    with pytest.raises(ValueError):
        release.parse(version)


def test_repository_is_consistent():
    assert release.check() == []
