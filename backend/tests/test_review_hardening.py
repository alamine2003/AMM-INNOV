"""Revue de septembre 2026 : durcissements d'autorisation, d'intégrité et d'exploitation."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from apps.amm.models import Renewal
from apps.amm.services.workflow import create_renewal, transition
from apps.documents.models import Document

pytestmark = pytest.mark.django_db


def pdf(name="scan.pdf", payload=b"same content"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n" + payload + b"\n%%EOF", "application/pdf")


# --- workflow : le statut ne change que par transition, et une seule ouverture à la fois


def test_renewal_status_cannot_be_patched_directly(hq_client, make_amm, make_renewal):
    renewal = make_renewal(make_amm(), "PLANIFIE")
    response = hq_client.patch(f"/api/v1/renewals/{renewal.pk}", {"workflow_status": "OBTENU"})
    assert response.status_code == 400
    assert "workflow_status" in response.json()
    renewal.refresh_from_db()
    assert renewal.workflow_status == "PLANIFIE"
    # les autres champs restent modifiables
    assert hq_client.patch(f"/api/v1/renewals/{renewal.pk}", {"notes": "ok"}).status_code == 200


def test_create_renewal_refuses_second_open_one(make_amm):
    amm = make_amm()
    first = create_renewal(amm, workflow_status="PLANIFIE")
    with pytest.raises(Exception, match="déjà en cours"):
        create_renewal(amm, workflow_status="PLANIFIE")
    transition(first, "ABANDONNE")
    assert create_renewal(amm, workflow_status="PLANIFIE").sequence == 2


def test_transition_rereads_current_status(make_amm, make_renewal):
    """Un objet périmé ne peut pas rejouer une transition déjà consommée par un autre acteur."""
    renewal = make_renewal(make_amm(), "PLANIFIE")
    stale = Renewal.objects.get(pk=renewal.pk)
    transition(renewal, "ABANDONNE")
    with pytest.raises(Exception, match="non autorisée"):
        transition(stale, "EN_PREPARATION")


# --- périmètre pays


def test_product_coverage_hides_other_countries(country_client, hq_client, make_amm, product):
    make_amm(country="SN", product_obj=product, start=date(2024, 1, 1))
    make_amm(country="CI", product_obj=product, start=date(2024, 1, 1))
    rows = {
        r["country_iso2"]: r
        for r in country_client.get(f"/api/v1/analytics/product/{product.pk}/coverage").json()
    }
    assert rows["SN"]["in_scope"] is True and rows["SN"]["status"] == "VALIDE"
    assert rows["CI"]["in_scope"] is False
    assert rows["CI"]["status"] is None and rows["CI"]["amm_id"] is None
    hq_rows = {
        r["country_iso2"]: r
        for r in hq_client.get(f"/api/v1/analytics/product/{product.pk}/coverage").json()
    }
    assert hq_rows["CI"]["status"] == "VALIDE"


def test_alert_cannot_be_assigned_outside_scope(hq_client, make_amm, rules, users):
    from apps.alerts.models import Alert
    from apps.alerts.services.engine import evaluate_rules
    from tests.conftest import TODAY

    amm = make_amm(
        country="CI",
        start=None,
        original_end_date=TODAY + date.resolution * 100,
        original_end_date_manual=True,
    )
    evaluate_rules(today=TODAY)
    alert = Alert.objects.filter(amm=amm).first()
    # users["country"] est limité à SN/ML : pas à CI
    denied = hq_client.post(f"/api/v1/alerts/{alert.pk}/assign", {"user_id": users["country"].pk})
    assert denied.status_code == 400
    ok = hq_client.post(f"/api/v1/alerts/{alert.pk}/assign", {"user_id": users["hq"].pk})
    assert ok.status_code == 200 and ok.json()["assigned_to_email"] == users["hq"].email


# --- documents : anti-doublon garanti par la base


def test_same_file_twice_is_refused_even_as_replacement(country_client, make_amm):
    amm = make_amm(start=date(2020, 1, 1))
    first = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": pdf(), "kind": "AMM"}, format="multipart"
    )
    assert first.status_code == 201
    again = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": pdf("copy.pdf")}, format="multipart"
    )
    assert again.status_code == 400 and "existe déjà" in again.json()["file"][0]
    same_as_replacement = country_client.post(
        f"/api/v1/documents/{first.json()['id']}/replace", {"file": pdf()}, format="multipart"
    )
    assert same_as_replacement.status_code == 400
    assert Document.objects.filter(amm=amm).count() == 1


def test_document_unique_constraint_exists():
    names = {c.name for c in Document._meta.constraints}
    assert "doc_amm_sha256_active_uniq" in names


# --- exploitation


def test_metrics_requires_token_when_configured(anon_client):
    assert anon_client.get("/metrics").status_code == 200
    with override_settings(METRICS_TOKEN="s3cret"):
        assert anon_client.get("/metrics").status_code == 401
        assert anon_client.get("/metrics", HTTP_AUTHORIZATION="Bearer nope").status_code == 401
        assert anon_client.get("/metrics", HTTP_AUTHORIZATION="Bearer s3cret").status_code == 200


def test_export_matches_filtered_list(hq_client, make_amm):
    make_amm(country="SN", start=date(2024, 1, 1))
    make_amm(country="CI", start=date(2024, 1, 1))
    listed = hq_client.get("/api/v1/amms?country=CI").json()["count"]
    csv = hq_client.get("/api/v1/analytics/export?format=csv&country=CI").content.decode()
    assert listed == 1 and csv.count("\n") == 2  # en-tête + 1 ligne


# --- images converties en PDF, documentation réservée aux connectés


def test_jpeg_upload_is_converted_to_pdf(country_client, make_amm):
    import io

    from PIL import Image

    amm = make_amm(start=date(2020, 1, 1))
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 30, 30)).save(buffer, format="JPEG")
    upload = SimpleUploadedFile("photo.jpg", buffer.getvalue(), "image/jpeg")
    response = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": upload, "kind": "AMM"}, format="multipart"
    )
    assert response.status_code == 201, response.json()
    assert response.json()["content_type"] == "application/pdf"
    assert response.json()["filename"].endswith(".pdf")
    document = Document.objects.get(pk=response.json()["id"])
    document.file.open("rb")
    assert document.file.read(4) == b"%PDF"
    document.file.close()


def test_corrupted_image_is_refused(country_client, make_amm):
    amm = make_amm(start=date(2020, 1, 1))
    upload = SimpleUploadedFile("broken.jpg", b"\xff\xd8\xff\xe0 not really a jpeg", "image/jpeg")
    response = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents", {"file": upload}, format="multipart"
    )
    assert response.status_code == 400 and "illisible" in response.json()["file"][0]


def test_api_docs_require_authentication(anon_client, hq_client):
    assert anon_client.get("/api/schema/").status_code in (401, 403)
    assert anon_client.get("/api/docs/").status_code in (401, 403)
    assert hq_client.get("/api/schema/").status_code == 200


def test_duplicate_amm_creation_is_a_400(hq_client, make_amm, product, countries):
    make_amm(country="SN", product_obj=product)
    response = hq_client.post(
        "/api/v1/amms", {"product": str(product.pk), "country": str(countries["SN"].pk)}
    )
    assert response.status_code == 400


# --- import à blanc, doublons de produits


def test_dry_run_import_writes_nothing_but_reports(hq_client, workbook_bytes, ranges):
    from apps.amm.models import MarketingAuthorization
    from apps.imports.models import ImportBatch
    from tests.conftest import TODAY

    upload = SimpleUploadedFile("classeur.xlsx", workbook_bytes)
    response = hq_client.post(
        "/api/v1/imports",
        {"file": upload, "today": TODAY.isoformat(), "dry_run": "true"},
        format="multipart",
    )
    assert response.status_code == 202, response.json()
    batch = response.json()
    assert batch["dry_run"] is True and batch["status"] == "DONE"
    assert batch["summary"]["dry_run"] is True
    assert batch["summary"]["totals"]["created"] == 7
    assert MarketingAuthorization.objects.count() == 0  # rien n'est écrit
    rows = hq_client.get(f"/api/v1/imports/{batch['id']}/rows").json()
    assert rows["count"] == 7 and all(r["amm"] is None for r in rows["results"])
    assert ImportBatch.objects.get(pk=batch["id"]).dry_run is True


def test_product_key_matches_punctuation_variants(ranges):
    from apps.catalog.models import Product
    from apps.catalog.normalize import product_key

    assert product_key("ACARBOSE GH 100 MG CPR B100") == product_key("ACARBOSE GH 100MG CPR B/100")
    product = Product.objects.create(name="ALFA GH SR 10MG CPR B/30")
    assert product.key == "ALFAGHSR10MGCPRB30"


def test_duplicate_groups_and_auto_merge(hq_client, ceo_client, make_amm, countries):
    from apps.catalog.models import Product, ProductAlias

    a = Product.objects.create(name="ALLOPURINOL GH 100MG CPR B/30")
    b = Product.objects.create(name="ALLOPURINOL GH 100MG CPR B30")
    make_amm(country="SN", product_obj=a)
    make_amm(country="CI", product_obj=a)
    make_amm(country="ML", product_obj=b)
    # groupe en conflit : deux produits avec une AMM au même pays
    c = Product.objects.create(name="ALFA GH SR 10MG CPR B/30")
    d = Product.objects.create(name="ALFA GH SR 10MG CPR B30")
    make_amm(country="SN", product_obj=c)
    make_amm(country="SN", product_obj=d)

    groups = hq_client.get("/api/v1/products/duplicates").json()
    assert len(groups) == 2
    clean = next(g for g in groups if not g["conflict"])
    assert clean["suggested_keep_id"] == str(a.pk)  # le plus d'AMM
    conflict = next(g for g in groups if g["conflict"])
    assert conflict["conflict_countries"] == ["SN"]

    assert hq_client.post("/api/v1/products/merge-duplicates", {}).status_code == 403
    result = ceo_client.post("/api/v1/products/merge-duplicates", {"dry_run": True}).json()
    assert result["merged_groups"] == 1 and Product.objects.filter(pk=b.pk).exists()
    result = ceo_client.post("/api/v1/products/merge-duplicates", {}).json()
    assert result["merged_groups"] == 1 and result["merged_products"] == 1
    assert len(result["conflicts"]) == 1
    assert not Product.objects.filter(pk=b.pk).exists()
    assert a.amms.count() == 3
    assert ProductAlias.objects.filter(product=a, raw_name=b.name).exists()
    # le conflit reste : seul le CEO peut trancher, via /products/{keep}/merge
    assert Product.objects.filter(pk__in=[c.pk, d.pk]).count() == 2


def test_import_reuses_product_with_different_punctuation(ranges, countries):
    from apps.catalog.models import Product
    from apps.imports.excel_parser import ParsedRow
    from apps.imports.services import _product_for

    existing = Product.objects.create(name="ADNA FENUGREC CPR EFFV B/10")
    row = ParsedRow.__new__(ParsedRow)
    row.raw_name = "ADNA FENUGREC CPR EFFV B10"
    row.product_name = "ADNA FENUGREC CPR EFFV B10"
    assert _product_for(row, None).pk == existing.pk
    assert Product.objects.count() == 1
