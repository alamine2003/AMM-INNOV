"""Import automatique : question « quelle AMM ? », points à vérifier (API), fichier perdu."""

from datetime import date

import pytest
from django.core.files.base import ContentFile

from apps.amm.models import MarketingAuthorization
from apps.catalog.models import Product
from apps.documents.models import Document
from apps.imports.models import DossierChange, DossierImport, DossierReviewPoint

from .conftest import MINIMAL_PDF, client_for
from .test_dossier_application import new_batch, stored
from .test_dossier_recognition import decision, staged

pytestmark = pytest.mark.django_db

API = "/api/v1/dossier-imports"
POINTS = "/api/v1/dossier-review-points"


def unknown_product_batch(user):
    """Décision d'un produit absent du catalogue : l'AMM cible n'est pas identifiable."""
    unknown = Product(name="PRODUIT INCONNU 5MG")
    batch = new_batch(user, root="DOSSIER RECU")
    stored(batch, "DOSSIER RECU/AMM_ORIGINE/decision.pdf", decision(unknown, start="28/04/2021"))
    stored(
        batch,
        "DOSSIER RECU/RENOUVELLEMENT_2026/decision.pdf",
        decision(unknown, start="28/04/2026", number="AMM/SN/2026/R9", renewal=True),
    )
    return batch


def analyze(client, batch):
    response = client.post(f"{API}/{batch.pk}/analyze", {}, format="json")
    assert response.status_code == 202, response.content
    batch.refresh_from_db()
    return batch


def test_question_then_manual_choice_ranges_the_documents(users, product, make_amm):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00152", start=date(2021, 4, 28)
    )
    client = client_for(users["country"])
    batch = analyze(client, unknown_product_batch(users["country"]))
    assert batch.status == DossierImport.Status.QUESTION
    assert batch.preview["question"]["reasons"]
    assert not Document.objects.exists()

    response = client.post(f"{API}/{batch.pk}/choose-amm", {"amm_id": str(amm.pk)}, format="json")
    assert response.status_code == 202, response.content
    batch.refresh_from_db()
    # Relu avec l'AMM choisie, puis rangé automatiquement : origine et renouvellement créé.
    assert batch.status == DossierImport.Status.APPLIED and batch.auto_applied
    assert batch.amm_id == amm.pk and batch.preview["forced"]
    renewal = amm.renewals.get()
    assert (renewal.number, renewal.workflow_status) == ("AMM/SN/2026/R9", "OBTENU")
    assert Document.objects.filter(amm=amm, renewal=renewal, kind="AMM").count() == 1
    assert Document.objects.filter(amm=amm, renewal__isnull=True, kind="AMM").count() == 1
    amm.refresh_from_db()
    assert amm.effective_end_date == date(2031, 4, 28) and amm.dossier_state == "COMPLET"
    # Le doute sur le produit n'est plus qu'un point à vérifier plus tard.
    assert DossierReviewPoint.objects.filter(amm=amm, code="identity").exists()
    detail = client.get(f"{API}/{batch.pk}").json()
    assert detail["open_points_count"] == len(detail["review_points"]) >= 1


def test_manual_choice_is_limited_to_the_user_scope(users, make_amm):
    elsewhere = make_amm(country="CI")
    client = client_for(users["country"])
    batch = analyze(client, unknown_product_batch(users["country"]))
    response = client.post(
        f"{API}/{batch.pk}/choose-amm", {"amm_id": str(elsewhere.pk)}, format="json"
    )
    assert response.status_code == 403
    batch.refresh_from_db()
    assert batch.amm_id is None and batch.status == DossierImport.Status.QUESTION


def test_ranged_dossier_is_not_ranged_again(users, product, make_amm):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00152", start=date(2025, 4, 28)
    )
    client = client_for(users["hq"])
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    batch = analyze(client, batch)
    assert batch.status == DossierImport.Status.APPLIED
    response = client.post(f"{API}/{batch.pk}/choose-amm", {"amm_id": str(amm.pk)}, format="json")
    assert response.status_code == 409
    assert client.post(f"{API}/{batch.pk}/analyze", {}, format="json").status_code == 409
    assert Document.objects.filter(amm=amm).count() == 1


def test_review_points_api_apply_ignore_and_scope(users, product, make_amm, countries):
    amm = make_amm(
        product_obj=product,
        original_number="AMM/SN/2025/00125",
        start=date(2025, 4, 28),
        holder="Ancien titulaire",
    )
    hq = client_for(users["hq"])
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    batch = analyze(hq, batch)
    assert batch.status == DossierImport.Status.APPLIED

    country = client_for(users["country"])
    listed = country.get(POINTS, {"amm": str(amm.pk), "status": "OPEN"}).json()
    by_field = {point["field"]: point for point in listed}
    assert set(by_field) == {"original_number", "holder"}
    assert (
        by_field["holder"]["applicable"] and by_field["holder"]["proof_name"] == "decision_amm.pdf"
    )
    amms = country.get("/api/v1/amms").json()["results"]
    assert next(row for row in amms if row["id"] == str(amm.pk))["open_review_points"] == 2

    response = country.post(f"{POINTS}/{by_field['holder']['id']}/apply")
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "APPLIED"
    amm.refresh_from_db()
    assert amm.holder == "Laboratoire Exemple"
    assert DossierChange.objects.get(amm=amm, field="holder").user == users["country"]

    response = country.post(f"{POINTS}/{by_field['original_number']['id']}/ignore")
    assert response.json()["status"] == "IGNORED"
    amm.refresh_from_db()
    assert amm.original_number == "AMM/SN/2025/00125"
    assert country.post(f"{POINTS}/{by_field['original_number']['id']}/apply").status_code == 400
    assert not country.get(POINTS, {"amm": str(amm.pk), "status": "OPEN"}).json()

    # Réglementaire d'un autre pays : les points de cette AMM ne lui sont pas visibles.
    users["country"].countries.set([countries["ML"]])
    assert country.get(POINTS, {"amm": str(amm.pk)}).json() == []
    assert country.post(f"{POINTS}/{by_field['holder']['id']}/ignore").status_code == 404


def test_lost_file_is_reported_clearly_instead_of_a_server_error(users, product, make_amm):
    amm = make_amm(product_obj=product)
    batch = new_batch(users["hq"])
    lost = staged(batch, "Dossier/AMM_ORIGINE/decision.pdf", decision(product))  # jamais écrit
    client = client_for(users["hq"])
    response = client.get(f"{API}/{batch.pk}/file", {"file_id": str(lost.pk)})
    assert response.status_code == 410
    assert response.json()["detail"].startswith("Fichier perdu")

    # Scan déposé perdu mais déjà rangé dans la fiche : on montre la copie rangée.
    document = Document(
        amm=amm,
        kind="AMM",
        document_date=date(2025, 4, 28),
        content_type="application/pdf",
        sha256="a" * 64,
        size_bytes=len(MINIMAL_PDF),
        uploaded_by=users["hq"],
    )
    document.file.save("document.pdf", ContentFile(MINIMAL_PDF), save=False)
    document.save()
    lost.document = document
    lost.save(update_fields=["document"])
    response = client.get(f"{API}/{batch.pk}/file", {"file_id": str(lost.pk)})
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == MINIMAL_PDF

    # Document de la fiche dont le fichier a disparu du stockage : même message explicite.
    document.file.storage.delete(document.file.name)
    response = client.get(f"/api/v1/documents/{document.pk}/file")
    assert response.status_code == 410 and response.json()["detail"].startswith("Fichier perdu")


def test_point_scan_is_served_to_the_country_user(users, product, make_amm):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00125", start=date(2025, 4, 28)
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    analyze(client_for(users["hq"]), batch)
    point = DossierReviewPoint.objects.get(amm=amm)
    # Le lot appartient au siège (invisible pour le pays) ; le scan du point reste accessible.
    country = client_for(users["country"])
    assert country.get(f"{API}/{batch.pk}").status_code == 404
    response = country.get(f"{POINTS}/{point.pk}/file")
    assert response.status_code == 200
    assert b"".join(response.streaming_content).startswith(b"%PDF")
    assert MarketingAuthorization.objects.get(pk=amm.pk).original_number == "AMM/SN/2025/00125"


def test_unreachable_storage_is_still_a_503_not_a_lost_file(users, product, monkeypatch):
    batch = new_batch(users["hq"])
    source = stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    storage = source.file.storage

    def down(*args, **kwargs):
        raise OSError("R2 injoignable")

    monkeypatch.setattr(storage, "open", down)
    monkeypatch.setattr(storage, "exists", down)
    response = client_for(users["hq"]).get(f"{API}/{batch.pk}/file", {"file_id": str(source.pk)})
    assert response.status_code == 503
