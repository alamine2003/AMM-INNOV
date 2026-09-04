import zipfile
from datetime import date
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from tests.conftest import MINIMAL_PDF

pytestmark = pytest.mark.django_db


def pdf(name="scan.pdf", suffix=b""):
    return SimpleUploadedFile(name, MINIMAL_PDF + suffix, content_type="application/pdf")


def test_upload_list_zip_and_file(country_client, make_amm, make_renewal):
    amm = make_amm(start=date(2019, 1, 1))
    renewal = make_renewal(amm, "OBTENU", number="R1", start_date=date(2024, 2, 2))

    first = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": pdf(), "kind": "AMM"}, format="multipart"
    )
    assert first.status_code == 201, first.json()
    assert first.json()["document_date"] == "2019-01-01"
    assert first.json()["period"] == "ORIGINAL"

    second = country_client.post(
        f"/api/v1/renewals/{renewal.pk}/documents",
        {"file": pdf("renouv.pdf", b"2"), "kind": "AMM", "title": "AMM renouvelée"},
        format="multipart",
    )
    assert second.status_code == 201, second.json()
    assert second.json()["document_date"] == "2024-02-02" and second.json()["renewal_id"] == str(
        renewal.pk
    )

    duplicate = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": pdf(), "kind": "AUTRE"}, format="multipart"
    )
    assert duplicate.status_code == 400 and "file" in duplicate.json()

    bad = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents",
        {"file": SimpleUploadedFile("x.txt", b"hello", content_type="text/plain"), "kind": "AMM"},
        format="multipart",
    )
    assert bad.status_code == 400

    listed = country_client.get(f"/api/v1/amms/{amm.pk}/documents").json()
    assert [d["document_date"] for d in listed] == ["2024-02-02", "2019-01-01"]
    grouped = country_client.get(f"/api/v1/amms/{amm.pk}/documents?group=period").json()
    assert [g["period"] for g in grouped] == ["RENEWAL", "ORIGINAL"]
    assert grouped[0]["documents"][0]["title"] == "AMM renouvelée"
    assert country_client.get(f"/api/v1/amms/{amm.pk}/documents?kind=COURRIER").json() == []

    amm_list = country_client.get("/api/v1/amms?has_current_scan=true").json()
    assert amm_list["count"] == 1 and amm_list["results"][0]["has_current_scan"] is True

    archive = country_client.get(f"/api/v1/amms/{amm.pk}/documents/archive.zip")
    assert archive.status_code == 200 and archive["Content-Type"] == "application/zip"
    names = zipfile.ZipFile(BytesIO(archive.content)).namelist()
    assert names[0].endswith("_AMM_2024-02-02.pdf") and names[1].endswith("_AMM_2019-01-01.pdf")

    doc_id = first.json()["id"]
    inline = country_client.get(f"/api/v1/documents/{doc_id}/file")
    assert inline.status_code == 200 and inline["Content-Type"] == "application/pdf"
    assert "inline" in inline["Content-Disposition"]
    assert b"".join(inline.streaming_content) == MINIMAL_PDF
    download = country_client.get(f"/api/v1/documents/{doc_id}/file?download=1")
    assert "attachment" in download["Content-Disposition"]

    detail = country_client.get(f"/api/v1/documents/{doc_id}").json()
    assert detail["sha256"] and detail["versions"] == []


def test_replace_delete_and_libraries(country_client, ceo_client, hq_client, make_amm):
    amm = make_amm(start=date(2020, 1, 1))
    created = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": pdf(), "kind": "AMM"}, format="multipart"
    ).json()
    replaced = country_client.post(
        f"/api/v1/documents/{created['id']}/replace",
        {"file": pdf("better.pdf", b"v2")},
        format="multipart",
    )
    assert replaced.status_code == 201 and replaced.json()["version"] == 2
    assert replaced.json()["versions"][0]["id"] == created["id"]
    current = country_client.get(f"/api/v1/amms/{amm.pk}/documents").json()
    assert [d["id"] for d in current] == [replaced.json()["id"]]
    everything = country_client.get(f"/api/v1/amms/{amm.pk}/documents?include_archived=1").json()
    assert len(everything) == 2

    assert country_client.delete(f"/api/v1/documents/{replaced.json()['id']}").status_code == 403
    assert hq_client.delete(f"/api/v1/documents/{replaced.json()['id']}").status_code == 403
    assert ceo_client.delete(f"/api/v1/documents/{replaced.json()['id']}").status_code == 204
    assert country_client.get(f"/api/v1/amms/{amm.pk}/documents").json() == []

    library = hq_client.get("/api/v1/countries/SN/documents").json()
    assert library["count"] == 0
    everything = hq_client.get("/api/v1/countries/SN/documents?include_archived=1").json()
    assert everything["count"] == 2
    assert country_client.get("/api/v1/countries/CI/documents").status_code == 403
    product_lib = hq_client.get(
        f"/api/v1/products/{amm.product_id}/documents?include_archived=1"
    ).json()
    assert product_lib["count"] == 2


def test_document_scope(country_client, hq_client, make_amm):
    amm = make_amm(country="CI")
    created = hq_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": pdf(), "kind": "AMM"}, format="multipart"
    )
    assert created.status_code == 201
    doc_id = created.json()["id"]
    assert country_client.get(f"/api/v1/documents/{doc_id}/file").status_code == 404
    assert (
        country_client.post(
            f"/api/v1/amms/{amm.pk}/documents", {"file": pdf(), "kind": "AMM"}, format="multipart"
        ).status_code
        == 404
    )
