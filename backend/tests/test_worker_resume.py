"""Render gratuit : reprise des analyses coupées, lecture réutilisée, maintien en éveil."""

import hashlib
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.core import worker
from apps.imports.dossier import extraction
from apps.imports.models import DossierFile, DossierImport
from tests.conftest import client_for

pytestmark = pytest.mark.django_db


def _file(batch, path, content=b"decision groupee", extraction_data=None):
    return DossierFile.objects.create(
        batch=batch,
        relative_path=path,
        file=f"staging/{path}",
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="application/pdf",
        size_bytes=len(content),
        extraction=extraction_data or {},
    )


def test_same_content_is_read_once(users, monkeypatch):
    """Les décisions groupées jointes à chaque produit ne sont lues qu'une fois."""
    first = DossierImport.objects.create(root_name="A", created_by=users["hq"])
    read = {"text": "Décision AMM", "source": "pdf_text", "errors": [], "warnings": []}
    _file(first, "A/decision.pdf", extraction_data=read)
    second = DossierImport.objects.create(root_name="B", created_by=users["hq"])
    upload = _file(second, "B/decision.pdf")
    calls = []
    monkeypatch.setattr(extraction, "extract_file", lambda record: calls.append(record) or {})
    assert extraction.load_extraction(upload) == read
    assert calls == []


def test_interrupted_reading_is_not_reused(users, monkeypatch):
    first = DossierImport.objects.create(root_name="A", created_by=users["hq"])
    cut = {"text": "", "errors": ["Délai OCR dépassé à la page 1."]}
    _file(first, "A/d.pdf", extraction_data=cut)
    upload = _file(DossierImport.objects.create(root_name="B", created_by=users["hq"]), "B/d.pdf")
    fresh = {"text": "lu", "errors": [], "warnings": []}
    monkeypatch.setattr(extraction, "extract_file", lambda record: fresh)
    assert extraction.load_extraction(upload) == fresh


def test_interrupted_analysis_resumes_at_worker_start(users):
    batch = DossierImport.objects.create(
        root_name="MALI - DOLEX",
        created_by=users["hq"],
        status=DossierImport.Status.RUNNING,
        started_at=timezone.now(),
        attempts=1,
    )
    with patch("apps.imports.tasks.analyze_dossier.delay") as delay:
        report = worker.resume_interrupted_analyses()
    batch.refresh_from_db()
    assert report == {"resumed": 1, "abandoned": 0}
    assert batch.status == DossierImport.Status.PENDING and batch.started_at is None
    delay.assert_called_once_with(str(batch.pk))


def test_analysis_that_keeps_crashing_ends_in_failure(users):
    batch = DossierImport.objects.create(
        root_name="MALI - LOURD",
        created_by=users["hq"],
        status=DossierImport.Status.RUNNING,
        attempts=worker.MAX_ATTEMPTS,
    )
    with patch("apps.imports.tasks.analyze_dossier.delay") as delay:
        report = worker.resume_interrupted_analyses()
    batch.refresh_from_db()
    assert report == {"resumed": 0, "abandoned": 1}
    assert batch.status == DossierImport.Status.FAILED and "3 fois" in batch.error
    delay.assert_not_called()


def test_each_analysis_counts_an_attempt_and_manual_retry_resets(users):
    from apps.imports import tasks

    batch = DossierImport.objects.create(root_name="X", created_by=users["hq"])
    tasks.analyze_dossier(str(batch.pk))
    batch.refresh_from_db()
    assert batch.attempts == 1
    DossierImport.objects.filter(pk=batch.pk).update(status=DossierImport.Status.FAILED)
    client = client_for(users["hq"])
    with patch("apps.imports.dossier_views.enqueue"):
        response = client.post(f"/api/v1/dossier-imports/{batch.pk}/analyze", {}, format="json")
    assert response.status_code == 202
    batch.refresh_from_db()
    assert batch.attempts == 0


def test_keepalive_pings_only_while_work_remains(users):
    with patch("urllib.request.urlopen") as urlopen:
        assert worker.ping_if_busy("https://api.example/api/v1/health/live") is False
        urlopen.assert_not_called()
        DossierImport.objects.create(root_name="X", created_by=users["hq"])
        assert worker.ping_if_busy("https://api.example/api/v1/health/live") is True
        urlopen.assert_called_once()
