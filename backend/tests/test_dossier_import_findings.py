"""Régressions trouvées en rejouant le dossier réel AMM_VILDAMET_SN (22/09/2026)."""

from datetime import date

import pytest

from apps.catalog.models import Product
from apps.imports.dossier.preview import build_preview
from apps.imports.models import DossierImport
from apps.imports.tasks import analyze_dossier

from .conftest import client_for
from .test_dossier_recognition import decision, staged

pytestmark = pytest.mark.django_db


def test_out_of_scope_country_user_still_sees_his_own_blocked_dossier(users, product):
    batch = DossierImport.objects.create(root_name="Dossier", created_by=users["country"])
    staged(batch, "Dossier/AMM_ORIGINE/decision.pdf", decision(product, country="Côte d'Ivoire"))
    analyze_dossier(str(batch.pk))
    batch.refresh_from_db()
    assert batch.status == DossierImport.Status.QUESTION
    response = client_for(users["country"]).get(f"/api/v1/dossier-imports/{batch.pk}/")
    assert response.status_code == 200
    question = response.json()["preview"]["question"]
    assert any("périmètre" in item for item in question["reasons"])


def test_receipt_document_date_is_the_filing_date(users, product):
    batch = DossierImport.objects.create(root_name="Dossier", created_by=users["hq"])
    staged(
        batch,
        "Dossier/RENOUVELLEMENT_2026/recepisse_depot.pdf",
        f"RECEPISSE DE DEPOT\nDossier de renouvellement {product.name}\nDepose le 01/03/2026\n",
    )
    receipt = build_preview(batch)["documents"][0]
    assert receipt["kind"] == "RECEPISSE"
    assert receipt["document_date"] == "2026-03-01"


def test_number_already_used_by_another_amm_of_the_country_is_flagged(
    users, product, make_amm, ranges
):
    other = Product.objects.create(name="AUTRE PRODUIT 10MG CPR B30", range=ranges["GENERALE"])
    make_amm(product_obj=other, original_number="AMM/SN/2025/00152")
    make_amm(product_obj=product, original_number="AMM/SN/2025/00151", start=date(2025, 4, 28))
    batch = DossierImport.objects.create(root_name="Dossier", created_by=users["hq"])
    staged(batch, "Dossier/AMM_ORIGINE/decision.pdf", decision(product))
    preview = build_preview(batch)
    assert any(
        "déjà attribué" in point["message"] and other.name in point["message"]
        for point in preview["review_points"]
    )
