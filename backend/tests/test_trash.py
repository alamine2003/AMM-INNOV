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
