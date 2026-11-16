"""1.2.2 : la corbeille. Rien n'est supprimé pour de bon ; un administrateur restaure."""

from datetime import date

import pytest

from apps.amm.models import MarketingAuthorization
from apps.catalog.models import Product
from apps.core.models import TrashEntry

pytestmark = pytest.mark.django_db


def test_trash_is_for_hq_and_ceo_only(country_client, hq_client):
    assert country_client.get("/api/v1/trash").status_code == 403
    assert hq_client.get("/api/v1/trash").status_code == 200


def test_deleted_amm_goes_to_the_trash_and_comes_back(hq_client, make_amm, make_renewal):
    amm = make_amm(original_start_date=date(2015, 1, 1))
    make_renewal(amm, status="OBTENU", number="R1", start_date=date(2020, 1, 1))
    assert hq_client.delete(f"/api/v1/amms/{amm.pk}").status_code == 204
    assert not MarketingAuthorization.objects.filter(pk=amm.pk).exists()
    entry = TrashEntry.objects.get(object_id=str(amm.pk))
    listed = hq_client.get("/api/v1/trash?state=deleted").json()["results"]
    assert [row["id"] for row in listed] == [str(entry.pk)] and listed[0]["rows"] >= 2
    hq_client.post(f"/api/v1/trash/{entry.pk}/restore")
    amm = MarketingAuthorization.objects.get(pk=amm.pk)
    assert amm.renewals.get().number == "R1"
    assert hq_client.get("/api/v1/trash?state=restored").json()["count"] == 1


def test_last_renewal_cancel_goes_to_the_trash(hq_client, make_amm, make_renewal):
    amm = make_amm(original_start_date=date(2010, 1, 1))
    make_renewal(amm, status="OBTENU", number="R1", start_date=date(2015, 1, 1))
    last = make_renewal(amm, status="OBTENU", number="R2", start_date=date(2020, 1, 1))
    assert hq_client.delete(f"/api/v1/renewals/{last.pk}").status_code == 204
    entry = TrashEntry.objects.get(object_id=str(last.pk))
    assert entry.kind == "renouvellement"
    hq_client.post(f"/api/v1/trash/{entry.pk}/restore")
    assert list(amm.renewals.order_by("sequence").values_list("number", flat=True)) == ["R1", "R2"]


def test_product_in_use_is_refused_unused_goes_to_the_trash(ceo_client, make_amm):
    used = make_amm().product
    response = ceo_client.delete(f"/api/v1/products/{used.pk}")
    assert response.status_code == 400 and "Encore utilisé" in response.json()["detail"]
    alone = Product.objects.create(name="SEUL GH 1MG CP B10")
    assert ceo_client.delete(f"/api/v1/products/{alone.pk}").status_code == 204
    entry = TrashEntry.objects.get(object_id=str(alone.pk))
    ceo_client.post(f"/api/v1/trash/{entry.pk}/restore")
    assert Product.objects.filter(pk=alone.pk).exists()


def test_user_is_deactivated_not_deleted(ceo_client, users):
    target = users["country"]
    assert ceo_client.delete(f"/api/v1/users/{target.pk}").status_code == 204
    target.refresh_from_db()
    assert target.is_active is False


# --- 1.3.2 : fiche rattachée à un import de dossier ------------------------------------------


@pytest.fixture
def filed_amm(users, make_amm, make_renewal, make_scan):
    """Une AMM rangée par un import de dossier, comme en production : l'import, son fichier
    source et sa traçabilité protègent la fiche, son renouvellement et son scan."""
    from apps.imports.models import DossierChange, DossierFile, DossierImport, DossierReviewPoint

    amm = make_amm(original_start_date=date(2015, 1, 1))
    renewal = make_renewal(amm, status="OBTENU", number="R1", start_date=date(2020, 1, 1))
    scan = make_scan(amm, renewal=renewal)
    batch = DossierImport.objects.create(
        root_name="LITACOLD", created_by=users["hq"], amm=amm, status="APPLIED"
    )
    source = DossierFile.objects.create(
        batch=batch,
        relative_path="LITACOLD/2020 - RENOUVELLEMENT.pdf",
        file=scan.file.name,
        sha256=scan.sha256,
        content_type="application/pdf",
        size_bytes=scan.size_bytes,
        document=scan,
    )
    # Un second import, sans fichier rattaché à un scan : il ne protège que la fiche.
    other = DossierImport.objects.create(root_name="LITACOLD (2)", created_by=users["hq"], amm=amm)
    for field, target in (("number", renewal), ("original_number", None)):
        DossierChange.objects.create(
            batch=batch,
            amm=amm,
            renewal=target,
            field=field,
            old_value="",
            new_value="R1",
            proof_file=source,
            confidence=90,
            user=users["hq"],
        )
    DossierReviewPoint.objects.create(
        batch=other, amm=amm, code="doubt", message="À vérifier.", fingerprint="f1"
    )
    return amm


def _counts(amm_pk) -> dict:
    from apps.amm.models import Renewal
    from apps.documents.models import Document
    from apps.imports.models import DossierChange, DossierFile, DossierImport, DossierReviewPoint

    return {
        "amm": MarketingAuthorization.objects.filter(pk=amm_pk).count(),
        "renewals": Renewal.objects.filter(amm_id=amm_pk).count(),
        "documents": Document.objects.filter(amm_id=amm_pk).count(),
        "imports": DossierImport.objects.filter(amm_id=amm_pk).count(),
        "files": DossierFile.objects.filter(batch__amm_id=amm_pk).count(),
        "changes": DossierChange.objects.filter(amm_id=amm_pk).count(),
        "points": DossierReviewPoint.objects.filter(amm_id=amm_pk).count(),
    }


FILED = {
    "amm": 1,
    "renewals": 1,
    "documents": 1,
    "imports": 2,
    "files": 1,
    "changes": 2,
    "points": 1,
}
GONE = dict.fromkeys(FILED, 0)


def test_amm_filed_by_a_dossier_import_goes_to_the_trash_and_comes_back(hq_client, filed_amm):
    """Régression (500 en production le 16/11/2026) : l'import de dossier et sa traçabilité
    protègent la fiche ; ils partent à la corbeille avec elle, et reviennent avec elle."""
    pk, status = filed_amm.pk, filed_amm.status
    assert _counts(pk) == FILED
    assert hq_client.delete(f"/api/v1/amms/{pk}").status_code == 204
    assert _counts(pk) == GONE
    entry = TrashEntry.objects.get()
    assert entry.object_id == str(pk) and entry.model == "amm.MarketingAuthorization"
    # Une seule entrée de corbeille, sans ligne copiée deux fois.
    copied = [(row["model"], row["pk"]) for row in entry.payload["objects"]]
    assert len(copied) == len(set(copied)) and copied[0] == ("amm.marketingauthorization", str(pk))

    assert hq_client.post(f"/api/v1/trash/{entry.pk}/restore").status_code == 200
    assert _counts(pk) == FILED
    restored = MarketingAuthorization.objects.get(pk=pk)
    assert restored.renewals.get().number == "R1" and restored.status == status


def test_binder_page_filed_by_a_dossier_import_is_deleted_and_restored(ceo_client, filed_amm):
    """Le même cas par « Supprimer la page » du classeur, puis « Annuler »."""
    from apps.binders.layout import binders_of

    pk, product = filed_amm.pk, filed_amm.product
    range_code = product.range.code if product.range_id else None
    key = next(b.key for b in binders_of(filed_amm.country) if b.contains(range_code, product.name))
    response = ceo_client.delete(f"/api/v1/binders/{key}/pages/{pk}")
    assert response.status_code == 200, response.content
    assert _counts(pk) == GONE
    # Supprimer deux fois ne montre pas d'erreur (1.2.6) et renvoie la même entrée.
    again = ceo_client.delete(f"/api/v1/binders/{key}/pages/{pk}")
    assert again.status_code == 200 and again["X-Trash-Entry"] == response["X-Trash-Entry"]
    assert ceo_client.post(f"/api/v1/trash/{response['X-Trash-Entry']}/restore").status_code == 200
    assert _counts(pk) == FILED


def test_protected_element_is_still_refused_without_the_option(filed_amm):
    """Sans `include_protected`, la protection joue comme avant : rien n'est supprimé."""
    from django.db.models import ProtectedError

    from apps.core.trash import move_to_trash

    with pytest.raises(ProtectedError):
        move_to_trash(filed_amm)
    assert _counts(filed_amm.pk) == FILED and not TrashEntry.objects.exists()
