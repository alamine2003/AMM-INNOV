"""L'état du dossier se déduit du scan de la décision en vigueur, jamais d'une déclaration."""

from datetime import date

import pytest

from apps.amm.models import MarketingAuthorization

pytestmark = pytest.mark.django_db

DS = MarketingAuthorization.DossierState


def test_without_a_scan_the_dossier_is_incomplete(make_amm):
    amm = make_amm(start=date(2024, 1, 1))
    assert amm.dossier_state == DS.INCOMPLET


def test_the_scan_of_the_original_decision_completes_the_dossier(make_amm, make_scan):
    amm = make_amm(start=date(2024, 1, 1))
    make_scan(amm)
    assert amm.dossier_state == DS.COMPLET


def test_a_receipt_is_not_the_decision(make_amm, make_scan):
    amm = make_amm(start=date(2024, 1, 1))
    make_scan(amm, kind="RECEPISSE")
    assert amm.dossier_state == DS.INCOMPLET


def test_a_new_renewal_moves_the_proof_to_its_own_decision(make_amm, make_scan, make_renewal):
    """Le scan de l'AMM d'origine ne prouve plus rien dès qu'un renouvellement fait foi."""
    amm = make_amm(start=date(2019, 1, 1))
    make_scan(amm)
    assert amm.dossier_state == DS.COMPLET

    renewal = make_renewal(amm, "OBTENU", number="R1", start_date=date(2026, 1, 1))
    amm.refresh_from_db()
    assert amm.effective_end_date == date(2031, 1, 1) and amm.dossier_state == DS.INCOMPLET

    make_scan(amm, renewal=renewal)
    assert amm.dossier_state == DS.COMPLET


def test_archiving_the_scan_reopens_the_dossier(make_amm, make_scan):
    amm = make_amm(start=date(2024, 1, 1))
    scan = make_scan(amm)
    assert amm.dossier_state == DS.COMPLET

    scan.is_current = False
    scan.save()
    amm.refresh_from_db()
    assert amm.dossier_state == DS.INCOMPLET


def test_uploading_the_scan_through_the_api_completes_the_dossier(country_client, make_amm):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from tests.conftest import MINIMAL_PDF

    amm = make_amm(country="SN", start=date(2024, 1, 1))
    assert amm.dossier_state == DS.INCOMPLET
    upload = SimpleUploadedFile("scan.pdf", MINIMAL_PDF, content_type="application/pdf")
    response = country_client.post(
        f"/api/v1/amms/{amm.pk}/documents",
        {"file": upload, "kind": "AMM"},
        format="multipart",
    )
    assert response.status_code == 201, response.json()
    amm.refresh_from_db()
    assert amm.dossier_state == DS.COMPLET
    assert country_client.get(f"/api/v1/amms/{amm.pk}").json()["dossier_state"] == "COMPLET"
