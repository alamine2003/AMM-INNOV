"""1.3.0 : sauvegardes de la base sur le serveur, copie hors machine et surveillance."""

import json
from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.administration.tasks import ship_backups
from apps.core import backups
from apps.core.integrity import IntegrityOptions
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db
PREFIX = "sauvegardes/base/"


def name_at(moment: datetime) -> str:
    return f"amm-vm-{moment.astimezone(UTC):%Y%m%d-%H%M%S}.dump.gpg"


class FakeObject:
    def __init__(self, bucket, key):
        self.bucket, self.key = bucket, key

    @property
    def content_length(self):
        return len(self.bucket.stored[self.key])

    def delete(self):
        del self.bucket.stored[self.key]


class FakeBucket:
    """Ce que le code utilise d'un bucket boto3 : lister, envoyer, relire la taille, retirer."""

    def __init__(self, truncate=False):
        self.stored: dict[str, bytes] = {}
        self.truncate = truncate
        self.objects = self

    def filter(self, Prefix):  # noqa: N803 (nom de boto3)
        return [FakeObject(self, key) for key in sorted(self.stored) if key.startswith(Prefix)]

    def upload_file(self, filename, key):
        with open(filename, "rb") as handle:
            data = handle.read()
        self.stored[key] = data[:-1] if self.truncate else data

    def Object(self, key):  # noqa: N802 (nom de boto3)
        return FakeObject(self, key)


@pytest.fixture
def server(tmp_path):
    """Un serveur : dossier des sauvegardes lu par le worker, stockage S3 simulé."""
    bucket = FakeBucket()
    with (
        override_settings(BACKUP_DIR=str(tmp_path), BACKUP_MAX_AGE_HOURS=30),
        mock.patch("apps.core.backups.remote_bucket", return_value=bucket),
    ):
        yield tmp_path, bucket


def write_backup(folder, moment, ok=True, error=""):
    """Ce que scripts/serveur/sauvegarder.sh laisse : le fichier vérifié et etat.json."""
    name = name_at(moment) if ok else ""
    if ok:
        (folder / name).write_bytes(b"chiffre-" + name.encode())
    at = f"{moment:%Y-%m-%dT%H:%M:%SZ}"
    state = {"at": at, "ok": ok, "file": name, "bytes": 0, "error": error}
    (folder / "etat.json").write_text(json.dumps(state))
    return name


# --- Hors serveur (Render) --------------------------------------------------------------------


def test_nothing_happens_without_a_backup_folder(users):
    assert ship_backups() == {"active": False}
    assert backups.backup_problems() == []
    assert not any(check.items for check in backups.check_backups(IntegrityOptions()))
    assert not Notification.objects.exists()


# --- Copie hors machine -----------------------------------------------------------------------


def test_verified_backups_are_copied_once(server, users):
    folder, bucket = server
    name = write_backup(folder, timezone.now() - timedelta(hours=1))
    (folder / "amm-vm-20261114-020000.echec").write_bytes(b"non relue")
    (folder / "amm-db-20261114-020000.sql.gz").write_bytes(b"ancien format, en clair")

    first = ship_backups()
    assert first["copied"] == [name] and first["problems"] == [] and first["notified"] == 0
    assert list(bucket.stored) == [PREFIX + name]
    assert bucket.stored[PREFIX + name] == (folder / name).read_bytes()

    second = ship_backups()
    assert second["copied"] == [] and second["problems"] == []


def test_incomplete_copy_is_a_problem_not_a_success(tmp_path, users):
    bucket = FakeBucket(truncate=True)
    write_backup(tmp_path, timezone.now() - timedelta(hours=1))
    with (
        override_settings(BACKUP_DIR=str(tmp_path)),
        mock.patch("apps.core.backups.remote_bucket", return_value=bucket),
    ):
        result = ship_backups()
    assert "copie incomplète" in result["error"] and result["copied"] == []


def test_remote_rotation_keeps_recent_and_the_last_seven(server):
    folder, bucket = server
    now = timezone.now()
    old = [name_at(now - timedelta(days=days)) for days in range(31, 43)]  # 12 anciennes
    recent = [name_at(now - timedelta(days=days)) for days in range(0, 3)]
    for name in old + recent:
        bucket.stored[PREFIX + name] = b"x"
    bucket.stored[PREFIX + "notes.txt"] = b"pas une sauvegarde"
    bucket.stored["documents/scan.pdf"] = b"un scan"

    result = backups.copy_offsite()
    kept = {key[len(PREFIX) :] for key in bucket.stored if key.startswith(PREFIX)}
    # 3 récentes + les 4 anciennes les plus récentes = 7 ; les 8 autres sont retirées.
    assert kept == {*recent, *sorted(old, reverse=True)[:4], "notes.txt"}
    assert len(result["removed"]) == 8
    assert "documents/scan.pdf" in bucket.stored


def test_expired_backup_still_on_the_server_is_not_sent_again(server):
    folder, bucket = server
    now = timezone.now()
    for days in range(0, 8):
        bucket.stored[PREFIX + name_at(now - timedelta(days=days))] = b"x"
    stale = name_at(now - timedelta(days=40))
    (folder / stale).write_bytes(b"ancienne, gardee plus longtemps sur le serveur")
    with override_settings(BACKUP_REMOTE_RETENTION_DAYS=5):
        first = backups.copy_offsite()
        second = backups.copy_offsite()
    assert first["copied"] == [] and len(first["removed"]) == 1
    assert second == {"active": True, "copied": [], "removed": []}
    assert PREFIX + stale not in bucket.stored


# --- Surveillance -----------------------------------------------------------------------------


def test_failed_backup_warns_the_ceo_once_a_day(server, users):
    folder, _ = server
    write_backup(folder, timezone.now() - timedelta(hours=26))
    ship_backups()
    write_backup(folder, timezone.now(), ok=False, error="la sauvegarde ne se restaure pas")

    result = ship_backups()
    assert result["notified"] == 1
    assert "a échoué" in result["problems"][0] and "ne se restaure pas" in result["problems"][0]
    assert ship_backups()["notified"] == 0
    notification = Notification.objects.get(user=users["ceo"])
    assert notification.channel == Notification.Channel.IN_APP
    assert notification.title == "Sauvegarde de la base : à vérifier"
    assert not Notification.objects.filter(user=users["hq"]).exists()


def test_backup_that_no_longer_runs_is_seen(server, users):
    folder, _ = server
    write_backup(folder, timezone.now() - timedelta(hours=31))
    problems = ship_backups()["problems"]
    assert any(p.startswith("Sauvegarde sur le serveur : la dernière date du") for p in problems)
    assert any(p.startswith("Copie hors du serveur") for p in problems)

    local, offsite = backups.check_backups(IntegrityOptions())
    assert local.code == "backup_verified" and local.severity == "ERROR" and local.items
    assert offsite.code == "backup_offsite" and offsite.severity == "WARNING" and offsite.items


def test_no_backup_yet_is_said_plainly(server, users):
    assert ship_backups()["problems"][0].startswith("Aucune sauvegarde n'a encore tourné")


def test_backup_kept_on_the_server_only_is_a_warning(tmp_path, users):
    write_backup(tmp_path, timezone.now() - timedelta(hours=1))
    with override_settings(BACKUP_DIR=str(tmp_path)):
        result = ship_backups()
        assert result["active"] is False and result["notified"] == 1
        local, offsite = backups.check_backups(IntegrityOptions())
        assert not local.items and "ne quittent pas le serveur" in offsite.items[0]
        _, skipped = backups.check_backups(IntegrityOptions(skip_storage=True))
        assert not skipped.items


def test_unreachable_remote_storage_is_reported(tmp_path, users):
    write_backup(tmp_path, timezone.now() - timedelta(hours=1))
    with (
        override_settings(BACKUP_DIR=str(tmp_path)),
        mock.patch("apps.core.backups.remote_bucket", side_effect=OSError("réseau coupé")),
    ):
        result = ship_backups()
    assert result["error"] == "réseau coupé"
    assert any("ne répond pas" in problem for problem in result["problems"])


def test_names_that_are_not_backups_are_ignored():
    assert backups.made_at("amm-vm-20261115-020007.dump.gpg") == datetime(
        2026, 11, 15, 2, 0, 7, tzinfo=UTC
    )
    for name in (
        "amm-vm-20261115-020007.dump",
        "amm-render-20261115-020007.dump.gpg",
        "amm-vm-20269915-020007.dump.gpg",
        "../amm-vm-20261115-020007.dump.gpg",
    ):
        assert backups.made_at(name) is None
