import hashlib
import io
import subprocess
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from pypdf import PdfWriter

from apps.catalog.models import Product
from apps.imports.dossier.extraction import extract_file
from apps.imports.dossier.preview import build_preview
from apps.imports.dossier.recognition import parse_date
from apps.imports.models import DossierFile, DossierImport

pytestmark = pytest.mark.django_db


def decision(
    product,
    *,
    number="AMM/SN/2025/00152",
    start="28/04/2025",
    country="Sénégal",
    renewal=False,
    holder="Laboratoire Exemple",
):
    return (
        f"République du {country}\nDécision officielle "
        f"{'de renouvellement' if renewal else 'd’autorisation de mise sur le marché'}\n"
        f"Produit : {product.name}\nPays : {country}\nTitulaire : {holder}\n"
        f"Numéro AMM : {number}\nDate de délivrance : {start}\n"
    )


def staged(batch, path, text, source="pdf_text", confidence=98, digest=None):
    return DossierFile.objects.create(
        batch=batch,
        relative_path=path,
        file=f"staging/{path}",
        sha256=digest or hashlib.sha256(text.encode()).hexdigest(),
        content_type="application/pdf",
        size_bytes=len(text),
        extraction={
            "text": text,
            "source": source,
            "confidence": confidence,
            "warnings": [],
            "errors": [],
            "page_count": 1,
        },
    )


@pytest.fixture
def batch(users):
    return DossierImport.objects.create(root_name="Dossier", created_by=users["hq"])


def test_official_wrong_number_matches_product_country_and_proposes_traceable_correction(
    batch,
    product,
    make_amm,
):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00125", start=date(2025, 4, 28)
    )
    proof = staged(batch, "AMM_ORIGINE/decision.pdf", decision(product))
    preview = build_preview(batch)
    assert preview["can_apply"], preview["blockers"]
    assert preview["amm"]["id"] == str(amm.pk)
    assert preview["level"] == "HIGH"
    correction = next(row for row in preview["changes"] if row["field"] == "original_number")
    assert correction["old"] == "AMM/SN/2025/00125"
    assert correction["new"] == "AMM/SN/2025/00152"
    assert correction["requires_confirmation"]
    assert correction["proof_file_id"] == str(proof.pk)
    amm.refresh_from_db()
    assert amm.original_number == "AMM/SN/2025/00125"
    assert preview == build_preview(batch)


def test_notice_does_not_override_official_decision(batch, product, make_amm):
    make_amm(product_obj=product)
    proof = staged(batch, "AMM_ORIGINE/decision.pdf", decision(product))
    staged(batch, "AMM_ORIGINE/notice.pdf", decision(product, number="INCORRECT"))
    preview = build_preview(batch)
    assert preview["can_apply"], preview["blockers"]
    assert preview["original"]["original_number"] == "AMM/SN/2025/00152"
    assert preview["original_proofs"]["original_number"] == str(proof.pk)
    assert (
        next(row for row in preview["documents"] if row["path"].endswith("notice.pdf"))["kind"]
        == "AUTRE"
    )


def test_conflicting_official_decisions_block(batch, product, make_amm):
    make_amm(product_obj=product)
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product))
    staged(batch, "AMM_ORIGINE/autre.pdf", decision(product, number="AMM/SN/2025/00222"))
    preview = build_preview(batch)
    assert not preview["can_apply"]
    assert any("contradictoires" in item for item in preview["blockers"])


def test_multiple_renewals_keep_original_and_existing_renewal_separate(
    batch,
    product,
    make_amm,
    make_renewal,
):
    amm = make_amm(product_obj=product, start=date(2020, 4, 28))
    renewal = make_renewal(amm, "OBTENU", start_date=date(2025, 4, 28), number="R-OLD")
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product, start="28/04/2020"))
    staged(
        batch,
        "RENOUVELLEMENT_2025/decision.pdf",
        decision(product, start="28/04/2025", number="R-CORRECTED", renewal=True),
    )
    staged(
        batch,
        "RENOUVELLEMENT_2030/decision.pdf",
        decision(product, start="28/04/2030", number="R-NEXT", renewal=True),
    )
    preview = build_preview(batch)
    assert preview["can_apply"], preview["blockers"]
    assert len(preview["renewals"]) == 2
    assert preview["renewals"][0]["existing_id"] == str(renewal.pk)
    assert preview["renewals"][1]["existing_id"] is None
    assert preview["original"]["original_start_date"] == "2020-04-28"
    assert any(
        row["field"] == "number" and row["old"] == "R-OLD" and row["requires_confirmation"]
        for row in preview["changes"]
    )
    assert amm.renewals.count() == 1


def test_country_user_never_sees_out_of_scope_candidate(batch, product, make_amm, users):
    make_amm(product_obj=product, country="CI")
    batch.created_by = users["country"]
    batch.save()
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product, country="Côte d'Ivoire"))
    preview = build_preview(batch)
    assert not preview["can_apply"] and preview["candidates"] == []
    assert any("périmètre" in item for item in preview["blockers"])


def test_mixed_products_or_countries_block(batch, product):
    second = Product.objects.create(name="AUTRE MEDICAMENT 50MG")
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product))
    staged(batch, "AMM_ORIGINE/autre.pdf", decision(second, country="Mali"))
    preview = build_preview(batch)
    assert not preview["can_apply"]
    assert any("plusieurs produits" in item for item in preview["blockers"])
    assert any("plusieurs pays" in item for item in preview["blockers"])


def test_same_amm_number_with_different_product_never_matches(batch, product, make_amm):
    other = Product.objects.create(name="AUTRE MEDICAMENT 50MG")
    make_amm(product_obj=other, original_number="AMM/SN/2025/00152")
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product))
    preview = build_preview(batch)
    assert preview["amm"]["id"] is None and preview["can_apply"]


def test_ocr_reliability_requires_review(batch, product, make_amm):
    make_amm(product_obj=product)
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product), source="ocr", confidence=80)
    preview = build_preview(batch)
    assert preview["can_apply"] and preview["level"] == "MEDIUM"
    assert all(row["requires_confirmation"] for row in preview["changes"])


def test_filename_only_cannot_create_or_modify(batch, product, make_amm):
    make_amm(product_obj=product)
    staged(batch, f"SN/{product.name}/AMM_ORIGINE/decision.pdf", "", confidence=0)
    preview = build_preview(batch)
    assert not preview["can_apply"] and preview["level"] == "LOW"
    assert preview["changes"] == []


def test_renewal_without_dated_decision_is_blocked(batch, product, make_amm):
    make_amm(product_obj=product)
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product))
    staged(batch, "RENOUVELLEMENT_2030/notice.pdf", "Notice du médicament")
    preview = build_preview(batch)
    assert not preview["can_apply"]
    assert any("décision officielle datée" in item for item in preview["blockers"])


def test_same_file_in_different_periods_is_blocked(batch, product, make_amm):
    make_amm(product_obj=product)
    staged(batch, "AMM_ORIGINE/decision.pdf", decision(product), digest="a" * 64)
    staged(
        batch,
        "RENOUVELLEMENT_2030/decision.pdf",
        decision(product, renewal=True, start="01/01/2030"),
        digest="a" * 64,
    )
    preview = build_preview(batch)
    assert not preview["can_apply"]
    assert any("fichier apparaît" in item for item in preview["blockers"])


def blank_pdf():
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(buffer)
    return SimpleNamespace(content_type="application/pdf", file=ContentFile(buffer.getvalue()))


def test_missing_ocr_binaries_are_reported_truthfully():
    with patch("apps.imports.dossier.extraction.shutil.which", return_value=None):
        result = extract_file(blank_pdf())
    assert result["source"] == "unreadable" and result["confidence"] == 0
    assert any("OCR indisponible" in error for error in result["errors"])


def test_ocr_subprocess_timeout_is_bounded_and_reported():
    with (
        patch("apps.imports.dossier.extraction.shutil.which", return_value="/bin/mock"),
        patch(
            "apps.imports.dossier.extraction.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pdftoppm", 25),
        ) as run,
    ):
        result = extract_file(blank_pdf())
    from apps.imports.dossier.extraction import OCR_TIMEOUT

    assert run.call_args.kwargs["timeout"] == OCR_TIMEOUT == 180
    assert any("Délai OCR dépassé" in error for error in result["errors"])


@pytest.mark.parametrize(
    "value,expected",
    [
        ("28 avril 2025", "2025-04-28"),
        ("2025-04-28", "2025-04-28"),
        ("31/02/2025", None),
        ("28/04/2025", "2025-04-28"),
    ],
)
def test_regulatory_dates(value, expected):
    assert parse_date(value) == expected


def test_interrupted_ocr_is_retried_on_reanalysis(users, monkeypatch):
    """Un délai OCR dépassé (Render gratuit, CPU réduit) ne fige pas l'extraction."""
    from apps.imports import tasks
    from apps.imports.dossier import extraction
    from apps.imports.models import DossierImport

    assert extraction.needs_retry({"errors": ["Délai OCR dépassé à la page 1."]})
    assert not extraction.needs_retry({"errors": ["Aucun texte exploitable dans le document."]})
    batch = DossierImport.objects.create(root_name="D", created_by=users["hq"])
    upload = staged(batch, "D/decision.pdf", "")
    upload.extraction = {"text": "", "errors": ["Délai OCR dépassé à la page 1."], "warnings": []}
    upload.save()
    calls = []

    def fake_extract(record):
        calls.append(record.pk)
        return {"text": "ok", "source": "ocr", "confidence": 80, "errors": [], "warnings": []}

    monkeypatch.setattr(extraction, "extract_file", fake_extract)
    monkeypatch.setattr("apps.imports.dossier.preview.extract_file", fake_extract)
    tasks.analyze_dossier(str(batch.pk))
    upload.refresh_from_db()
    assert calls == [upload.pk] and upload.extraction["text"] == "ok"
