"""Classement autonome : l'application tranche seule et ne signale que ce qui exige une action."""

from datetime import date

import pytest

from apps.amm.models import MarketingAuthorization
from apps.catalog.models import Product
from apps.imports.dossier.report import build_report
from apps.imports.models import DossierImport, DossierReviewPoint
from apps.notifications.models import Notification

from .conftest import client_for
from .test_dossier_application import new_batch, stored
from .test_dossier_auto_apply import analyze
from .test_dossier_recognition import decision

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def autonomous(settings):
    settings.DOSSIER_AUTONOMOUS = True
    settings.DOSSIER_AUTO_APPLY = True
    settings.DOSSIER_AUTO_CREATE = True


def test_official_decision_corrects_the_record(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    """Écart scan ≠ fiche : la décision officielle fait foi, l'ancienne valeur reste tracée."""
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00999", start=date(2025, 4, 28)
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    batch = analyze(batch, django_capture_on_commit_callbacks)

    assert batch.status == DossierImport.Status.APPLIED and batch.auto_applied
    amm.refresh_from_db()
    assert amm.original_number == "AMM/SN/2025/00152"
    fixed = [f for f in batch.summary["fields_changed"] if f["corrected"]]
    assert fixed == [
        {
            "target": "amm",
            "field": "original_number",
            "label": fixed[0]["label"],
            "old": "AMM/SN/2025/00999",
            "new": "AMM/SN/2025/00152",
            "corrected": True,
        }
    ]
    assert not DossierReviewPoint.objects.filter(amm=amm, code="value_mismatch").exists()
    # Historique : l'ancienne valeur est gardée dans le journal des changements du lot.
    assert batch.audit.get(field="original_number").old_value == "AMM/SN/2025/00999"
    # Pas une notification par produit rangé seul : le récapitulatif les regroupe.
    assert not Notification.objects.filter(title__startswith="Import de dossier").exists()


def test_correction_never_puts_the_end_before_the_start(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    amm = make_amm(
        product_obj=product,
        original_number="AMM/SN/2025/00152",
        start=date(2019, 1, 1),
        original_end_date=date(2020, 1, 1),
        original_end_date_manual=True,
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2025"))
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.APPLIED
    amm.refresh_from_db()
    # Début 2025 après une fin 2020 : aucune correction, l'écart reste un point.
    assert amm.original_start_date == date(2019, 1, 1)
    assert DossierReviewPoint.objects.filter(amm=amm, code="value_mismatch").exists()


def test_near_name_is_attached_to_the_catalog_product(
    users, product, make_amm, ranges, django_capture_on_commit_callbacks
):
    """« ARTEGEN 120MG PDRE SOL INJT » (coquille) : rattaché à ARTEGEN 120MG PDRE SOL INJ."""
    amm = make_amm(product_obj=product, original_number="AMM/SN/2025/00152")
    typo = Product(name="ARTEGEN 120MG PDRE SOL INJT", range=ranges["GENERALE"])
    batch = new_batch(users["hq"], root="SENEGAL - ARTEGEN")
    stored(batch, "SENEGAL - ARTEGEN/AMM_ORIGINE/decision_amm.pdf", decision(typo))
    batch = analyze(batch, django_capture_on_commit_callbacks)

    assert batch.status == DossierImport.Status.APPLIED and batch.amm_id == amm.pk
    assert not Product.objects.filter(name__endswith="INJT").exists()


def test_absent_product_is_created_with_its_amm(users, django_capture_on_commit_callbacks):
    class Named:
        name = "NOUVEAUGEN 50MG CP B10"

    batch = new_batch(users["hq"], root="SENEGAL - NOUVEAUGEN 50MG CP B10")
    stored(
        batch,
        "SENEGAL - NOUVEAUGEN 50MG CP B10/AMM/decision.pdf",
        decision(Named, number="AMM/SN/2024/00777", start="02/05/2024"),
    )
    batch = analyze(batch, django_capture_on_commit_callbacks)

    assert batch.status == DossierImport.Status.APPLIED and batch.summary["created"]
    amm = MarketingAuthorization.objects.get(pk=batch.amm_id)
    assert amm.original_number == "AMM/SN/2024/00777"
    assert amm.original_start_date == date(2024, 5, 2)


def test_unreadable_dossier_is_filed_in_a_new_record_and_flagged(
    users, django_capture_on_commit_callbacks
):
    """Aucune décision lisible : la fiche du produit est créée quand même, à compléter."""
    batch = new_batch(users["hq"], root="SENEGAL - INCONNUGEN 10MG")
    stored(batch, "SENEGAL - INCONNUGEN 10MG/scan.pdf", "Courrier illisible République du Sénégal")
    batch = analyze(batch, django_capture_on_commit_callbacks)

    assert batch.status == DossierImport.Status.APPLIED
    amm = MarketingAuthorization.objects.select_related("product").get(pk=batch.amm_id)
    assert amm.product.name == "INCONNUGEN 10MG" and amm.country.iso2 == "SN"
    assert amm.documents.count() == 1
    codes = set(DossierReviewPoint.objects.filter(amm=amm).values_list("code", flat=True))
    assert {"incomplete", "unreadable"} <= codes

    report = build_report(DossierImport.objects.all())
    assert report["totals"]["created"] == 1
    assert {item["kind"] for item in report["attention"]} == {"incomplete"}


def test_report_lists_only_what_needs_action(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00999", start=date(2025, 4, 28)
    )
    good = new_batch(users["hq"])
    stored(good, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    analyze(good, django_capture_on_commit_callbacks)
    empty = DossierImport.objects.create(
        root_name="VIDE", created_by=users["hq"], status=DossierImport.Status.FAILED, error="x"
    )

    response = client_for(users["hq"]).get("/api/v1/dossier-imports/report?days=7")
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["filed"] == 1 and body["totals"]["corrected"] == 1
    assert body["corrections"][0]["amm_id"] == str(amm.pk)
    assert body["corrections"][0]["old"] == "AMM/SN/2025/00999"
    assert [item["batch_id"] for item in body["attention"]] == [str(empty.pk)]
    assert body["attention"][0]["kind"] == "failed"


def test_generic_folder_name_never_becomes_a_product(users, django_capture_on_commit_callbacks):
    batch = new_batch(users["hq"], root="AMM_PRODUIT")
    stored(batch, "AMM_PRODUIT/scan.pdf", "Courrier illisible République du Sénégal")
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.QUESTION
    assert not Product.objects.filter(name__icontains="AMM").exists()
    report = build_report(DossierImport.objects.all())
    assert [item["kind"] for item in report["attention"]] == ["question"]
