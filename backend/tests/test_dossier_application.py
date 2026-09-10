"""Application d'un dossier validé : rattachements, créations, corrections, audit, idempotence."""

import hashlib
from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from apps.amm.history import amm_history
from apps.amm.models import MarketingAuthorization
from apps.documents.models import Document
from apps.imports.dossier.application import StalePreview, apply_dossier, preview_token
from apps.imports.dossier.preview import build_preview
from apps.imports.models import DossierChange, DossierFile, DossierImport

from .test_dossier_recognition import decision

pytestmark = pytest.mark.django_db


def stored(batch, path, text):
    """Fichier réellement écrit dans le stockage, extraction pré-calculée (pas d'OCR)."""
    content = f"%PDF-1.4\n{text}".encode()
    record = DossierFile(
        batch=batch,
        relative_path=path,
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="application/pdf",
        size_bytes=len(content),
        extraction={
            "text": text,
            "source": "pdf_text",
            "confidence": 98,
            "warnings": [],
            "errors": [],
            "page_count": 1,
        },
    )
    record.file.save(path.rsplit("/", 1)[-1], ContentFile(content), save=False)
    record.save()
    return record


def ready(batch):
    """Ce que fait la tâche Celery `analyze_dossier`."""
    preview = build_preview(batch)
    batch.preview = preview
    batch.preview_token = preview_token(preview)
    batch.status = DossierImport.Status.READY
    batch.country_id = preview["amm"]["country_id"]
    batch.save()
    return preview


def new_batch(user, root="AMM_PRODUIT"):
    return DossierImport.objects.create(root_name=root, created_by=user)


def test_apply_attaches_documents_corrects_number_and_is_idempotent(users, product, make_amm):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00125", start=date(2025, 4, 28)
    )
    batch = new_batch(users["hq"])
    proof = stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/notice.pdf", "Notice\n" + decision(product, number="X"))
    preview = ready(batch)
    assert preview["can_apply"], preview["blockers"]
    correction = next(c for c in preview["changes"] if c["field"] == "original_number")
    holder = next(c for c in preview["changes"] if c["field"] == "holder")
    assert correction["requires_confirmation"] and not holder["requires_confirmation"]

    applied = apply_dossier(
        batch.pk, user=users["hq"], token=batch.preview_token, accepted_changes=[correction["id"]]
    )
    assert applied.status == DossierImport.Status.APPLIED and applied.amm_id == amm.pk
    amm.refresh_from_db()
    assert amm.original_number == "AMM/SN/2025/00152"
    assert amm.holder == "Laboratoire Exemple"
    documents = Document.objects.filter(amm=amm).order_by("kind")
    assert [d.kind for d in documents] == ["AMM", "AUTRE"]
    assert all(d.renewal_id is None for d in documents)
    assert set(DossierFile.objects.filter(batch=batch).values_list("document_id", flat=True)) == {
        d.pk for d in documents
    }
    change = DossierChange.objects.get(amm=amm, field="original_number")
    assert (change.old_value, change.new_value) == ("AMM/SN/2025/00125", "AMM/SN/2025/00152")
    assert change.proof_file == proof and change.user == users["hq"] and change.confidence >= 90
    # Champ vide complété : journalisé aussi, l'ancienne valeur étant la chaîne vide.
    completion = DossierChange.objects.get(amm=amm, field="holder")
    assert not completion.old_value and completion.new_value == "Laboratoire Exemple"
    entry = next(e for e in amm_history(amm) if e["type"] == "documentary_correction")
    assert entry["changes"][0]["field"] == "original_number"
    assert entry["document_id"] == str(proof.document_id)
    # Un document créé par l'import ne partage pas son fichier avec la preuve du dossier.
    assert proof.document.file.name != proof.file.name

    # Seconde confirmation du même lot : aucun effet.
    again = apply_dossier(
        batch.pk, user=users["hq"], token=batch.preview_token, accepted_changes=[correction["id"]]
    )
    assert again.pk == batch.pk and Document.objects.filter(amm=amm).count() == 2

    # Même dossier importé une seconde fois : doublons reconnus, rien n'est recréé.
    second = new_batch(users["hq"])
    stored(second, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    stored(second, "AMM_PRODUIT/AMM_ORIGINE/notice.pdf", "Notice\n" + decision(product, number="X"))
    preview2 = ready(second)
    assert preview2["can_apply"], preview2["blockers"]
    assert all(row["duplicate_id"] for row in preview2["documents"])
    assert preview2["changes"] == []
    apply_dossier(second.pk, user=users["hq"], token=second.preview_token, accepted_changes=[])
    assert Document.objects.filter(amm=amm).count() == 2
    assert MarketingAuthorization.objects.filter(product=product).count() == 1
    assert DossierChange.objects.filter(amm=amm).count() == 2


def test_apply_creates_amm_then_renewal_with_provenance(users, product, countries):
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2019"))
    stored(
        batch,
        "AMM_PRODUIT/RENOUVELLEMENT_2024/decision.pdf",
        decision(product, start="28/04/2024", number="AMM/SN/2024/R1", renewal=True),
    )
    preview = ready(batch)
    assert preview["can_apply"], preview["blockers"]
    assert preview["amm"]["id"] is None and preview["renewals"][0]["existing_id"] is None

    apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token, accepted_changes=[])
    amm = MarketingAuthorization.objects.get(product=product, country=countries["SN"])
    assert amm.original_number == "AMM/SN/2025/00152"
    assert amm.original_start_date == date(2019, 4, 28)
    assert amm.holder == "Laboratoire Exemple"
    renewal = amm.renewals.get()
    assert renewal.workflow_status == "OBTENU"
    assert renewal.number == "AMM/SN/2024/R1" and renewal.start_date == date(2024, 4, 28)
    assert renewal.end_date == date(2029, 4, 28)
    assert amm.effective_end_date == date(2029, 4, 28) and amm.status == "VALIDE"
    assert Document.objects.filter(amm=amm, renewal=renewal, kind="AMM").count() == 1
    assert Document.objects.filter(amm=amm, renewal__isnull=True, kind="AMM").count() == 1
    creation = DossierChange.objects.filter(amm=amm, renewal__isnull=True, field="original_number")
    assert creation.get().reason == "Création depuis le dossier réglementaire"
    assert DossierChange.objects.filter(amm=amm, renewal=renewal, field="number").exists()


def test_pending_renewal_is_completed_instead_of_duplicated(users, product, make_amm, make_renewal):
    amm = make_amm(product_obj=product, start=date(2021, 4, 28))
    pending = make_renewal(amm, "DEPOSE", filing_date=date(2026, 3, 1))
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2021"))
    stored(
        batch,
        "AMM_PRODUIT/RENOUVELLEMENT_2026/decision.pdf",
        decision(product, start="20/08/2026", number="AMM/SN/2026/R1", renewal=True),
    )
    preview = ready(batch)
    assert preview["can_apply"], preview["blockers"]
    assert preview["renewals"][0]["existing_id"] == str(pending.pk)
    status_change = next(c for c in preview["changes"] if c["field"] == "workflow_status")
    assert (status_change["old"], status_change["new"]) == ("DEPOSE", "OBTENU")
    assert status_change["requires_confirmation"]

    apply_dossier(
        batch.pk,
        user=users["hq"],
        token=batch.preview_token,
        accepted_changes=[status_change["id"]],
    )
    assert amm.renewals.count() == 1
    pending.refresh_from_db()
    assert pending.workflow_status == "OBTENU"
    assert pending.number == "AMM/SN/2026/R1" and pending.start_date == date(2026, 8, 20)
    assert pending.filing_date == date(2026, 3, 1)
    amm.refresh_from_db()
    assert amm.effective_end_date == date(2031, 8, 20)
    assert DossierChange.objects.filter(renewal=pending, field="workflow_status").exists()


def test_unaccepted_correction_is_kept_and_stale_token_refused(users, product, make_amm):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00125", start=date(2025, 4, 28)
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    ready(batch)
    with pytest.raises(StalePreview):
        apply_dossier(batch.pk, user=users["hq"], token="0" * 64, accepted_changes=[])
    apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token, accepted_changes=[])
    amm.refresh_from_db()
    assert amm.original_number == "AMM/SN/2025/00125"
    assert amm.holder == "Laboratoire Exemple"
    assert not DossierChange.objects.filter(amm=amm, field="original_number").exists()
    assert Document.objects.filter(amm=amm).count() == 1


def test_low_confidence_or_blocked_preview_cannot_be_applied(users, product, make_amm):
    make_amm(product_obj=product)
    batch = new_batch(users["hq"])
    only_filename = DossierFile.objects.create(
        batch=batch,
        relative_path="AMM_PRODUIT/AMM_ORIGINE/decision.pdf",
        file="staging/decision.pdf",
        sha256="0" * 64,
        content_type="application/pdf",
        size_bytes=1,
        extraction={
            "text": "",
            "source": "unreadable",
            "confidence": 0,
            "warnings": [],
            "errors": [],
        },
    )
    preview = ready(batch)
    assert not preview["can_apply"] and preview["level"] == "LOW"
    with pytest.raises(ValidationError):
        apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token, accepted_changes=[])
    assert only_filename.document_id is None
    assert not Document.objects.exists() and not DossierChange.objects.exists()
