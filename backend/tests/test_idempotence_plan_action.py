"""1.2.6 : suppressions idempotentes, imports qui ne recréent pas ce qui a été supprimé,
rangement qui dit pourquoi il n'a pas rangé (par ordre d'urgence), plan d'action."""

from datetime import date, timedelta

import pytest

from apps.amm.models import MarketingAuthorization
from apps.catalog.models import Product
from apps.core.models import ErrorEvent, TrashEntry
from apps.imports.models import DossierImport

from .conftest import TODAY
from .test_dossier_application import new_batch, stored
from .test_dossier_recognition import decision

pytestmark = pytest.mark.django_db


# --- Suppressions idempotentes ---------------------------------------------------------------


def test_deleting_an_amm_twice_never_fails(hq_client, make_amm):
    amm = make_amm()
    first = hq_client.delete(f"/api/v1/amms/{amm.pk}")
    assert first.status_code == 204 and first["X-Trash-Entry"]
    again = hq_client.delete(f"/api/v1/amms/{amm.pk}")
    assert again.status_code == 204
    assert again["X-Trash-Entry"] == first["X-Trash-Entry"]
    assert TrashEntry.objects.filter(object_id=str(amm.pk)).count() == 1


def test_unknown_element_is_still_not_found(hq_client):
    response = hq_client.delete("/api/v1/amms/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_country_user_does_not_see_trash_of_other_countries(hq_client, country_client, make_amm):
    amm = make_amm(country="CI")
    assert hq_client.delete(f"/api/v1/amms/{amm.pk}").status_code == 204
    # Hors de son périmètre : rien n'indique que l'élément a existé.
    assert country_client.delete(f"/api/v1/amms/{amm.pk}").status_code in (403, 404)


def test_catalog_and_rules_deletions_are_idempotent(hq_client, rules):
    alone = Product.objects.create(name="SEUL GH 1MG CP B10")
    for _ in range(2):
        assert hq_client.delete(f"/api/v1/products/{alone.pk}").status_code == 204
    rule = next(iter(rules.values()))
    for _ in range(2):
        assert hq_client.delete(f"/api/v1/alert-rules/{rule.pk}").status_code == 204


def test_renewal_and_scan_deletions_are_idempotent(hq_client, make_amm, make_renewal, make_scan):
    amm = make_amm()
    renewal = make_renewal(amm, status="PLANIFIE")
    first = hq_client.delete(f"/api/v1/renewals/{renewal.pk}")
    assert first.status_code == 204 and first["X-Trash-Entry"]
    assert hq_client.delete(f"/api/v1/renewals/{renewal.pk}").status_code == 204
    document = make_scan(amm)
    assert hq_client.delete(f"/api/v1/documents/{document.pk}").status_code == 204
    document.refresh_from_db()
    archived = document.archived_at
    assert hq_client.delete(f"/api/v1/documents/{document.pk}").status_code == 204
    document.refresh_from_db()
    assert document.archived_at == archived  # rien n'est refait


def test_binder_page_deleted_twice_returns_the_same_trash_entry(
    hq_client, make_amm, django_capture_on_commit_callbacks
):
    amm = make_amm(product_obj=Product.objects.create(name="DOUBLE GH 5MG CPR B30"))
    url = "/api/v1/binders/SN-generale-a-k"
    with django_capture_on_commit_callbacks(execute=True):
        first = hq_client.delete(f"{url}/pages/{amm.pk}")
        again = hq_client.delete(f"{url}/pages/{amm.pk}")
    assert first.status_code == 200, first.json()
    assert again.status_code == 200, again.json()
    assert again["X-Trash-Entry"] == first["X-Trash-Entry"]


# --- Ce qui est supprimé ne revient pas par un import ------------------------------------------


def test_excel_import_does_not_recreate_a_deleted_amm(hq_client, workbook_path):
    from apps.imports.models import ImportBatch, ImportRow
    from apps.imports.services import import_workbook

    import_workbook(str(workbook_path), today=TODAY)
    amm = MarketingAuthorization.objects.order_by("product__name").first()
    assert hq_client.delete(f"/api/v1/amms/{amm.pk}").status_code == 204
    batch = ImportBatch.objects.create()
    import_workbook(str(workbook_path), batch=batch, today=TODAY)
    assert not MarketingAuthorization.objects.filter(
        product_id=amm.product_id, country_id=amm.country_id
    ).exists()
    row = ImportRow.objects.filter(batch=batch, message__contains="corbeille").get()
    assert row.outcome == "SKIPPED"
    # Restaurée : elle est de nouveau suivie par les imports.
    entry = TrashEntry.objects.get(object_id=str(amm.pk))
    assert hq_client.post(f"/api/v1/trash/{entry.pk}/restore").status_code == 200
    import_workbook(str(workbook_path), today=TODAY)
    assert MarketingAuthorization.objects.filter(pk=amm.pk).exists()


def test_registry_does_not_recreate_an_amm_deleted_from_the_list(hq_client, make_amm, tmp_path):
    from apps.imports.services import import_workbook

    from .test_registry_import import registry, row

    amm = make_amm(product_obj=Product.objects.create(name="EFFACE GH 5MG CPR B30"))
    assert hq_client.delete(f"/api/v1/amms/{amm.pk}").status_code == 204
    source = registry(
        tmp_path, [row(Presentation="EFFACE GH 5MG CPR B30", Source="Classement seul")]
    )
    import_workbook(source)
    assert not MarketingAuthorization.objects.filter(product__name__startswith="EFFACE").exists()


def test_dossier_does_not_recreate_a_deleted_amm(
    hq_client, users, product, make_amm, django_capture_on_commit_callbacks
):
    from apps.imports.tasks import analyze_dossier

    amm = make_amm(product_obj=product)
    assert hq_client.delete(f"/api/v1/amms/{amm.pk}").status_code == 204
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    with django_capture_on_commit_callbacks(execute=True):
        analyze_dossier(str(batch.pk))
    batch.refresh_from_db()
    assert batch.status == DossierImport.Status.QUESTION
    assert batch.preview["question"]["codes"] == ["deleted_amm"]
    assert not batch.preview["question"]["can_create"]
    assert (
        "corbeille" in hq_client.get(f"/api/v1/dossier-imports/{batch.pk}").json()["status_reason"]
    )
    assert not MarketingAuthorization.objects.filter(product=product).exists()


# --- Rangement : rangé, ou la raison est dite ---------------------------------------------------


def test_failed_filing_says_why_and_is_journaled(
    users, product, make_amm, monkeypatch, hq_client, django_capture_on_commit_callbacks
):
    from django.core.exceptions import ValidationError

    from apps.imports.tasks import analyze_dossier

    make_amm(product_obj=product, original_number="AMM/SN/2025/00152", start=date(2019, 4, 28))
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2019"))

    def refuse(*args, **kwargs):
        raise ValidationError("La preuve documentaire est absente du dossier.")

    monkeypatch.setattr("apps.imports.dossier.application.apply_dossier", refuse)
    with django_capture_on_commit_callbacks(execute=True):
        analyze_dossier(str(batch.pk))
    batch.refresh_from_db()
    assert batch.status == DossierImport.Status.READY
    assert batch.error == "Non rangé : La preuve documentaire est absente du dossier."
    body = hq_client.get(f"/api/v1/dossier-imports/{batch.pk}").json()
    assert body["status_reason"] == batch.error
    event = ErrorEvent.objects.get(kind="Rangement automatique")
    assert event.source == "worker" and "preuve documentaire" in event.message
    report = hq_client.get("/api/v1/dossier-imports/report").json()
    assert [item["reason"] for item in report["attention"]] == [batch.error]


def test_ready_reason_without_error_says_what_happens(settings, users):
    from apps.imports.dossier.preview import PREVIEW_VERSION
    from apps.imports.dossier.report import ready_reason

    batch = new_batch(users["hq"])
    batch.preview = {"version": PREVIEW_VERSION, "amm": {"id": "x"}}
    settings.DOSSIER_AUTO_APPLY = False
    assert "désactivé" in ready_reason(batch)
    settings.DOSSIER_AUTO_APPLY = True
    assert "ordre d'urgence" in ready_reason(batch)
    batch.preview["version"] = PREVIEW_VERSION - 1
    assert "règles plus anciennes" in ready_reason(batch)


def test_waiting_dossiers_are_filed_most_urgent_first(users, make_amm):
    from apps.imports.hooks import by_regulatory_urgency

    valid = make_amm(status="VALIDE", effective_end_date=TODAY + timedelta(days=900))
    soon = make_amm(status="A_RENOUVELER", effective_end_date=TODAY + timedelta(days=90))
    expired = make_amm(status="EXPIRE", effective_end_date=TODAY - timedelta(days=10))
    MarketingAuthorization.objects.filter(pk=valid.pk).update(status="VALIDE")
    MarketingAuthorization.objects.filter(pk=soon.pk).update(status="A_RENOUVELER")
    MarketingAuthorization.objects.filter(pk=expired.pk).update(status="EXPIRE")
    batches = []
    for amm in (None, valid, soon, expired):
        batch = new_batch(users["hq"])
        batch.preview = {"amm": {"id": str(amm.pk) if amm else None}}
        batches.append(batch)
    ordered = by_regulatory_urgency(batches)
    targets = [b.preview["amm"]["id"] for b in ordered]
    assert targets == [str(expired.pk), str(soon.pk), str(valid.pk), None]


# --- Plan d'action -----------------------------------------------------------------------------


def _plan(client, **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    body = client.get(f"/api/v1/amms/action-plan?{query}").json()
    return {category["gap"]: category for category in body["categories"]}, body


def test_action_plan_lists_amms_without_origin_or_renewal(
    hq_client, make_amm, make_renewal, make_scan
):
    no_origin = make_amm(original_number="")
    no_renewal = make_amm(start=date(2010, 1, 1))  # origine échue en 2015, rien après
    renewed = make_amm(start=date(2010, 1, 1))
    renewal = make_renewal(
        renewed,
        status="OBTENU",
        number="R1",
        start_date=date(2015, 1, 1),
        end_date=date(2020, 1, 1),
    )
    complete = make_amm()
    make_scan(complete)

    plan, body = _plan(hq_client)
    assert list(plan) == [
        "no_original",
        "missing_renewal",
        "to_file",
        "original_scan",
        "renewal_scan",
    ]
    ids = {gap: [item["id"] for item in plan[gap]["items"]] for gap in plan}
    assert ids["no_original"] == [str(no_origin.pk)]
    assert ids["missing_renewal"] == [str(no_renewal.pk)]
    assert str(renewed.pk) not in ids["missing_renewal"]
    assert str(renewed.pk) in ids["to_file"]  # renouvelée jusqu'en 2020 : à redéposer
    assert str(renewed.pk) in ids["renewal_scan"]
    assert str(complete.pk) not in ids["original_scan"]
    assert body["total"] == 3 and plan["original_scan"]["count"] == 3
    make_scan(renewed, renewal=renewal)
    plan, _ = _plan(hq_client)
    assert plan["renewal_scan"]["count"] == 0


def test_action_plan_is_ordered_by_urgency_and_scoped(country_client, make_amm):
    later = make_amm(original_number="", country="SN")
    sooner = make_amm(original_number="", country="ML")
    other = make_amm(original_number="", country="CI")
    MarketingAuthorization.objects.filter(pk=later.pk).update(
        status="VALIDE", effective_end_date=TODAY + timedelta(days=800)
    )
    MarketingAuthorization.objects.filter(pk=sooner.pk).update(
        status="EXPIRE", effective_end_date=TODAY - timedelta(days=5)
    )
    plan, _ = _plan(country_client)
    ids = [item["id"] for item in plan["no_original"]["items"]]
    assert ids == [str(sooner.pk), str(later.pk)]
    assert str(other.pk) not in ids  # Côte d'Ivoire : hors de son périmètre
    plan, _ = _plan(country_client, country="SN")
    assert [item["id"] for item in plan["no_original"]["items"]] == [str(later.pk)]


def test_amm_list_filters_by_gap(hq_client, make_amm):
    no_origin = make_amm(original_start_date=None)
    make_amm()
    listed = hq_client.get("/api/v1/amms?gap=no_original").json()["results"]
    assert [row["id"] for row in listed] == [str(no_origin.pk)]
    assert hq_client.get("/api/v1/amms?gap=nope").status_code == 400
