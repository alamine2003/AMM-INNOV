"""`manage.py check_integrity` : muet sur des données saines, bavard sur des violations plantées."""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.amm.models import MarketingAuthorization, Renewal


def run_check(*args) -> dict:
    out = StringIO()
    try:
        call_command("check_integrity", "--json", *args, stdout=out)
    except SystemExit as exc:
        assert exc.code == 1
    return json.loads(out.getvalue())


@pytest.mark.django_db
def test_clean_data_passes(make_amm, make_scan, make_renewal):
    amm = make_amm()
    make_scan(amm)
    report = run_check()
    assert report["ok"] is True, report["violations"]


@pytest.mark.django_db
def test_planted_violations_are_reported(make_amm, make_scan, users):
    from apps.imports.models import DossierImport
    from apps.notifications.models import Notification

    # modification sans historique (UPDATE appliqué, INSERT d'historique perdu)
    edited = make_amm(notes="avant")
    MarketingAuthorization.objects.filter(pk=edited.pk).update(notes="après")
    # statut stocké incohérent
    stale = make_amm()
    MarketingAuthorization.objects.filter(pk=stale.pk).update(status="EXPIRE")
    # deux renouvellements ouverts
    both = make_amm()
    Renewal.objects.create(amm=both, workflow_status="PLANIFIE")
    Renewal.objects.create(amm=both, workflow_status="DEPOSE", filing_date=timezone.localdate())
    # deux versions courantes du même document (remplacements concurrents)
    from django.core.files.base import ContentFile

    from apps.documents.models import Document

    forked = make_scan(make_amm())
    for i in range(2):
        twin = Document(
            amm=forked.amm, kind=forked.kind, document_date=forked.document_date,
            sha256=f"{i}" * 64, replaces=forked, version=2,
        )
        twin.file.save(f"v{i}.pdf", ContentFile(b"%PDF-1.4 twin"), save=True)
    # fichier référencé mais disparu
    lost = make_scan(make_amm())
    lost.file.storage.delete(lost.file.name)
    # e-mail jamais parti, analyse bloquée
    notification = Notification.objects.create(user=users["ceo"], channel="EMAIL", title="x")
    Notification.objects.filter(pk=notification.pk).update(
        created_at=timezone.now() - timedelta(hours=2)
    )
    batch = DossierImport.objects.create(root_name="d", created_by=users["ceo"], status="RUNNING")
    DossierImport.objects.filter(pk=batch.pk).update(created_at=timezone.now() - timedelta(hours=2))

    report = run_check()
    assert report["ok"] is False
    for code in (
        "history_matches_rows",
        "amm_state_consistent",
        "single_open_renewal",
        "single_current_version",
        "referenced_file_exists",
        "email_delivered",
        "no_stuck_job",
    ):
        assert report["violations"].get(code), code
