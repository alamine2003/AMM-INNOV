"""Document ingestion: ordering, grouping, duplicates, versions."""

from datetime import date, timedelta
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.documents.models import Document
from apps.documents.services.archive import build_archive
from apps.documents.services.ingest import detect_content_type, ingest_document
from tests.conftest import MINIMAL_PDF

pytestmark = pytest.mark.django_db


def upload(content: bytes = MINIMAL_PDF, name: str = "scan.pdf"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def test_detect_content_type():
    assert detect_content_type(b"%PDF-1.7 ...") == "application/pdf"
    assert detect_content_type(b"\xff\xd8\xff\xe0JFIF") == "image/jpeg"
    assert detect_content_type(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert detect_content_type(b"GIF89a") is None


def test_ingest_sets_metadata_and_path(make_amm, users):
    amm = make_amm(start=date(2024, 1, 15))
    document = ingest_document(amm, upload(), "AMM", user=users["country"])
    assert document.document_date == date(2024, 1, 15)
    assert document.sha256 and document.size_bytes == len(MINIMAL_PDF)
    assert document.version == 1 and document.is_current
    assert document.file.name.startswith(
        f"documents/SN/{amm.product.slug}/{amm.pk}/2024-01-15_AMM_v1_"
    )
    assert document.file.name.endswith(".pdf")
    assert document.export_filename().startswith("SN_") and document.export_filename().endswith(
        "_AMM_2024-01-15.pdf"
    )


def test_duplicate_sha256_refused(make_amm):
    amm = make_amm()
    ingest_document(amm, upload(), "AMM")
    with pytest.raises(ValidationError) as exc:
        ingest_document(amm, upload(), "AUTRE")
    assert "file" in exc.value.message_dict
    # same file on another AMM is fine
    ingest_document(make_amm(), upload(), "AMM")


def test_rejects_non_pdf_and_too_large(make_amm, settings):
    amm = make_amm()
    with pytest.raises(ValidationError):
        ingest_document(amm, upload(b"GIF89a....", "x.gif"), "AMM")
    settings.DOCUMENT_MAX_MB = 1
    with pytest.raises(ValidationError):
        ingest_document(amm, upload(b"%PDF-1.4" + b"0" * (1024 * 1024 + 10)), "AMM")


def test_ordering_most_recent_first(make_amm):
    amm = make_amm(start=date(2020, 1, 1))
    old = ingest_document(amm, upload(MINIMAL_PDF + b"a"), "AMM", document_date=date(2020, 1, 1))
    new = ingest_document(
        amm, upload(MINIMAL_PDF + b"b"), "COURRIER", document_date=date(2025, 3, 1)
    )
    same_day_first = ingest_document(
        amm, upload(MINIMAL_PDF + b"c"), "RECEPISSE", document_date=date(2025, 3, 1)
    )
    Document.objects.filter(pk=same_day_first.pk).update(
        uploaded_at=timezone.now() - timedelta(days=1)
    )
    ordered = list(Document.objects.filter(amm=amm))
    assert [d.pk for d in ordered] == [new.pk, same_day_first.pk, old.pk]


def test_grouping_by_period(make_amm, make_renewal):
    from apps.documents.views import _group_by_period

    amm = make_amm(start=date(2018, 1, 1))
    renewal = make_renewal(amm, "OBTENU", number="R1", start_date=date(2023, 1, 1))
    origin_doc = ingest_document(amm, upload(MINIMAL_PDF + b"1"), "AMM")
    renewal_doc = ingest_document(amm, upload(MINIMAL_PDF + b"2"), "AMM", renewal=renewal)
    assert renewal_doc.document_date == date(2023, 1, 1)
    groups = _group_by_period(amm, list(Document.objects.filter(amm=amm)))
    assert [g["period"] for g in groups] == ["RENEWAL", "ORIGINAL"]
    assert groups[0]["sequence"] == 1
    assert groups[0]["documents"][0]["id"] == str(renewal_doc.pk)
    assert groups[1]["documents"][0]["id"] == str(origin_doc.pk)


def test_replace_creates_new_version(make_amm, users):
    amm = make_amm()
    first = ingest_document(amm, upload(MINIMAL_PDF + b"v1"), "AMM")
    second = ingest_document(
        amm, upload(MINIMAL_PDF + b"v2"), "AMM", replaces=first, user=users["ceo"]
    )
    first.refresh_from_db()
    assert second.version == 2 and second.replaces_id == first.pk
    assert first.is_current is False and second.is_current is True
    assert list(Document.objects.current().filter(amm=amm)) == [second]


def test_archive_zip_order_and_names(make_amm):
    import zipfile

    amm = make_amm(start=date(2020, 1, 1))
    ingest_document(amm, upload(MINIMAL_PDF + b"1"), "AMM", document_date=date(2020, 1, 1))
    ingest_document(amm, upload(MINIMAL_PDF + b"2"), "COURRIER", document_date=date(2024, 5, 5))
    payload = build_archive(list(Document.objects.filter(amm=amm)))
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        names = archive.namelist()
    assert len(names) == 2
    assert names[0].endswith("_COURRIER_2024-05-05.pdf")
    assert names[1].endswith("_AMM_2020-01-01.pdf")
    assert names[0].startswith("SN_")
