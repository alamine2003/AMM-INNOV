"""Chronologie d'une page de classeur : corriger périodes et pièces faussées par la lecture auto."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.amm.models import Renewal
from apps.catalog.models import Product
from apps.documents.models import Document
from tests.conftest import MINIMAL_PDF

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def archivist_in_country_can_edit(monkeypatch):
    """Ces tests décrivent le travail de l'archiviste, réglementaire pays compris (portée des
    pays, valeurs relues…). Depuis la 1.2.1, seuls le CEO et le siège modifient un classeur par
    défaut : le droit est ouvert ici à tous les rôles. La lecture seule est testée dans
    tests/test_binders_read_only.py."""
    from apps.accounts import roles

    monkeypatch.setitem(roles.ACTION_ROLES, roles.Action.BINDER_EDIT, roles.ALL_ROLES)

URL = "/api/v1/binders/SN-generale-a-k"


@pytest.fixture
def alfa(make_amm, ranges, make_renewal, make_scan):
    """Le cas d'ALFA GH SR 10MG : un import a créé le renouvellement 2 en double du 1, avec
    la décision lue au 20/08/2026 et le récépissé ; le renouvellement 1 n'a plus de scan."""
    product = Product.objects.create(name="ALFA GH SR 10MG CPR B30", range=ranges["GENERALE"])
    amm = make_amm(
        product_obj=product, original_start_date=date(2020, 6, 23), original_number="9315"
    )
    first = make_renewal(amm, status="OBTENU", number="9315", start_date=date(2025, 6, 23))
    second = make_renewal(amm, status="OBTENU", number="9315", start_date=date(2025, 6, 23))
    make_scan(amm)
    decision = make_scan(amm, renewal=second)
    decision.document_date = date(2026, 8, 20)
    decision.save()
    receipt = Document.objects.create(
        amm=amm,
        renewal=second,
        kind="RECEPISSE",
        document_date=date(2026, 1, 8),
        file=SimpleUploadedFile("recepisse.pdf", MINIMAL_PDF + b"recepisse"),
        sha256="recepisse",
    )
    return {"amm": amm, "first": first, "second": second, "decision": decision, "receipt": receipt}


def _page(body):
    return body["sections"][0]["pages"][0]


def _entry(page, renewal=None):
    wanted = str(renewal.pk) if renewal else None
    kind = "renewal" if renewal else "origin"
    return next(
        e for e in page["chronology"] if e["kind"] == kind and e.get("renewal_id") == wanted
    )


def _period_url(amm, period):
    return f"{URL}/pages/{amm.pk}/periods/{period}"


def test_duplicate_renewal_is_cancelled_and_its_scans_move(
    hq_client, alfa, django_capture_on_commit_callbacks
):
    amm, first, second = alfa["amm"], alfa["first"], alfa["second"]
    with django_capture_on_commit_callbacks(execute=True):
        response = hq_client.delete(f"{_period_url(amm, second.pk)}?move_to={first.pk}")
    assert response.status_code == 200, response.json()
    page = _page(response.json())

    assert not Renewal.objects.filter(pk=second.pk).exists()
    labels = [e["label"] for e in page["chronology"]]
    assert labels == ["Renouvellement 1", "AMM d'origine"]
    first_entry = _entry(page, first)
    assert [d["document_id"] for d in first_entry["decisions"]] == [str(alfa["decision"].pk)]
    assert [d["kind"] for d in first_entry["others"]] == ["RECEPISSE"]
    assert first_entry["issues"] == []  # le « décision non scannée » a disparu
    assert Document.objects.current().filter(amm=amm).count() == 3  # rien d'archivé
    amm.refresh_from_db()
    assert (amm.status, amm.dossier_state) == ("VALIDE", "COMPLET")
    assert (page["status"], page["dossier_state"]) == ("VALIDE", "COMPLET")


def test_older_passage_without_scan_is_removed_and_no_scan_is_lost(
    hq_client, country_client, alfa, django_capture_on_commit_callbacks
):
    """Un passage qui n'existe pas (renouvellement 1 sans scan) se supprime, même s'il n'est pas
    le plus récent ; seul le siège ou le CEO le peut, et aucune pièce n'est archivée."""
    amm, first, second = alfa["amm"], alfa["first"], alfa["second"]
    assert country_client.delete(_period_url(amm, first.pk)).status_code == 403
    with django_capture_on_commit_callbacks(execute=True):
        response = hq_client.delete(_period_url(amm, first.pk))
    assert response.status_code == 200, response.json()
    page = _page(response.json())
    assert not Renewal.objects.filter(pk=first.pk).exists()
    second.refresh_from_db()
    assert second.sequence == 1  # l'ordre est recalculé
    assert [e["label"] for e in page["chronology"]] == ["Renouvellement 1", "AMM d'origine"]
    assert Document.objects.current().filter(amm=amm).count() == 3


def test_removed_passage_scans_go_to_the_origin_by_default(hq_client, alfa):
    amm, second = alfa["amm"], alfa["second"]
    response = hq_client.delete(_period_url(amm, second.pk))
    assert response.status_code == 200, response.json()
    origin = _entry(_page(response.json()))
    assert str(alfa["decision"].pk) in [d["document_id"] for d in origin["decisions"]]
    assert Document.objects.current().filter(amm=amm).count() == 3


def test_period_dates_and_number_are_corrected(country_client, alfa):
    amm, first = alfa["amm"], alfa["first"]
    response = country_client.patch(
        _period_url(amm, first.pk),
        {"start_date": "2025-06-24", "number": " 9315-R1 "},
        format="json",
    )
    assert response.status_code == 200, response.json()
    entry = _entry(_page(response.json()), first)
    # Date de fin recalculée depuis la durée de validité du pays (5 ans).
    assert (entry["number"], entry["start_date"], entry["end_date"]) == (
        "9315-R1",
        "2025-06-24",
        "2030-06-24",
    )
    first.refresh_from_db()
    assert first.history.first().history_user.email == "sn@test.local"

    # Date de fin saisie : elle fait foi ; effacée : elle redevient calculée.
    entry = _entry(
        _page(
            country_client.patch(
                _period_url(amm, first.pk), {"end_date": "2030-01-01"}, format="json"
            ).json()
        ),
        first,
    )
    assert entry["end_date"] == "2030-01-01"
    first.refresh_from_db()
    assert first.end_date_manual is True
    entry = _entry(
        _page(
            country_client.patch(
                _period_url(amm, first.pk), {"end_date": None}, format="json"
            ).json()
        ),
        first,
    )
    assert entry["end_date"] == "2030-06-24"


def test_origin_is_corrected_and_cannot_be_deleted(country_client, alfa):
    amm = alfa["amm"]
    response = country_client.patch(
        _period_url(amm, "origin"), {"start_date": "2020-06-22"}, format="json"
    )
    origin = _entry(_page(response.json()))
    assert (origin["start_date"], origin["end_date"]) == ("2020-06-22", "2025-06-22")
    assert country_client.delete(_period_url(amm, "origin")).status_code == 403


def test_end_before_start_is_refused(country_client, alfa):
    response = country_client.patch(
        _period_url(alfa["amm"], alfa["first"].pk), {"end_date": "2020-01-01"}, format="json"
    )
    assert response.status_code == 400


def test_document_date_and_period_are_corrected(country_client, alfa):
    amm, decision, first = alfa["amm"], alfa["decision"], alfa["first"]
    response = country_client.patch(
        f"{URL}/pages/{amm.pk}/documents/{decision.pk}",
        {"document_date": "2025-06-23", "period": str(first.pk)},
        format="json",
    )
    assert response.status_code == 200, response.json()
    entry = _entry(_page(response.json()), first)
    assert entry["decisions"][0]["document_date"] == "2025-06-23"
    decision.refresh_from_db()
    assert decision.renewal_id == first.pk

    # Vers l'AMM d'origine.
    page = _page(
        country_client.patch(
            f"{URL}/pages/{amm.pk}/documents/{decision.pk}", {"period": "origin"}, format="json"
        ).json()
    )
    assert len(_entry(page)["decisions"]) == 2


def test_period_of_another_amm_is_refused(country_client, alfa, make_amm, make_renewal):
    other = make_renewal(make_amm(), status="OBTENU", start_date=date(2024, 1, 1))
    response = country_client.patch(
        f"{URL}/pages/{alfa['amm'].pk}/documents/{alfa['decision'].pk}",
        {"period": str(other.pk)},
        format="json",
    )
    assert response.status_code == 400


def test_only_ceo_and_headquarters_remove_a_document(country_client, hq_client, alfa):
    amm, receipt = alfa["amm"], alfa["receipt"]
    url = f"{URL}/pages/{amm.pk}/documents/{receipt.pk}"
    # Même règle que la suppression d'un scan sur la fiche AMM (1.0.7) : CEO et siège.
    assert country_client.delete(url).status_code in (403, 404)
    response = hq_client.delete(url)
    assert response.status_code == 200
    second = _entry(_page(response.json()), alfa["second"])
    assert second["others"] == []
    receipt.refresh_from_db()
    assert receipt.archived_at is not None  # archivée : l'historique la garde


def test_document_is_added_on_the_chosen_period(country_client, alfa):
    amm, first = alfa["amm"], alfa["first"]
    response = country_client.post(
        f"{URL}/pages/{amm.pk}/documents",
        {
            "file": SimpleUploadedFile(
                "r1.pdf", MINIMAL_PDF + b"r1", content_type="application/pdf"
            ),
            "kind": "AMM",
            "document_date": "2025-06-23",
            "period": str(first.pk),
        },
        format="multipart",
    )
    assert response.status_code == 201, response.json()
    entry = _entry(_page(response.json()), first)
    assert [d["document_date"] for d in entry["decisions"]] == ["2025-06-23"]
    assert entry["issues"] == []


def test_country_scope_and_binder_are_enforced(country_client, alfa, make_amm, ranges):
    ci = make_amm(country="CI")
    response = country_client.patch(
        f"/api/v1/binders/CI/pages/{ci.pk}/periods/origin", {"number": "X"}, format="json"
    )
    assert response.status_code == 404
    cardio = make_amm(product_obj=Product.objects.create(name="AMLO", range=ranges["CARDIO"]))
    response = country_client.patch(_period_url(cardio, "origin"), {"number": "X"}, format="json")
    assert response.status_code == 403


def test_corrected_period_start_recomputes_its_end(country_client, alfa):
    amm, first = alfa["amm"], alfa["first"]
    first.end_date = first.start_date.replace(year=first.start_date.year + 3)
    first.end_date_manual = True
    first.save()
    new_start = first.start_date.replace(day=1)
    response = country_client.patch(
        f"{URL}/pages/{amm.pk}/periods/{first.pk}",
        {"start_date": new_start.isoformat()},
        format="json",
    )
    assert response.status_code == 200, response.content
    first.refresh_from_db()
    assert first.end_date == new_start.replace(year=new_start.year + 5)
    assert not first.end_date_manual


def test_page_title_is_renamed_everywhere_and_old_name_still_matches(
    hq_client, country_client, alfa
):
    from apps.catalog.models import ProductAlias

    amm = alfa["amm"]
    url = f"{URL}/pages/{amm.pk}"
    assert country_client.patch(url, {"product_name": "X"}, format="json").status_code == 403
    response = hq_client.patch(url, {"product_name": "alfa gh sr 10mg  cpr b/30"}, format="json")
    assert response.status_code == 200, response.json()
    amm.refresh_from_db()
    assert amm.product.name == "ALFA GH SR 10MG CPR B/30"
    # L'ancien nom reste reconnu par les imports.
    alias = ProductAlias.objects.get(raw_name="ALFA GH SR 10MG CPR B30")
    assert alias.product_id == amm.product_id
    other = Product.objects.create(name="AUTRE PRODUIT")
    response = hq_client.patch(url, {"product_name": other.name}, format="json")
    assert response.status_code == 400 and "fusionnez" in str(response.json())


def test_page_is_deleted_everywhere_and_its_scans_are_taken_by_another_record(
    hq_client, make_amm, alfa, django_capture_on_commit_callbacks
):
    from apps.amm.models import MarketingAuthorization
    from apps.binders.models import BinderDeletedPage

    amm = alfa["amm"]
    keep = make_amm(product_obj=Product.objects.create(name="ALFA GH 10MG CPR B30"))
    url = f"{URL}/pages/{amm.pk}"
    # Des pièces : il faut une fiche qui les reprend.
    response = hq_client.delete(url)
    assert response.status_code == 400 and "3 pièces" in str(response.json())
    with django_capture_on_commit_callbacks(execute=True):
        response = hq_client.delete(f"{url}?move_to_amm={keep.pk}")
    assert response.status_code == 200, response.json()
    assert not MarketingAuthorization.objects.filter(pk=amm.pk).exists()
    assert Document.objects.current().filter(amm=keep).count() == 3
    deleted = BinderDeletedPage.objects.get()
    assert (
        deleted.product_name == "ALFA GH SR 10MG CPR B30" and deleted.moved_to == keep.product.name
    )


def test_deleted_page_is_not_recreated_by_the_registry(hq_client, make_amm, countries, tmp_path):
    from apps.amm.models import MarketingAuthorization
    from apps.imports.services import import_workbook
    from tests.test_registry_import import registry, row

    amm = make_amm(product_obj=Product.objects.create(name="FANTOME GH 5MG CPR B30"))
    assert hq_client.delete(f"{URL}/pages/{amm.pk}").status_code == 200
    source = registry(
        tmp_path,
        [row(Presentation="FANTOME GH 5MG CPR B30", Source="Classement seul")],
    )
    import_workbook(source)
    assert not MarketingAuthorization.objects.filter(product__name__startswith="FANTOME").exists()


def test_gap_is_ignored_without_adding_a_passage(country_client, make_amm, make_renewal):
    amm = make_amm(
        product_obj=Product.objects.create(name="GAPGEN 5MG CPR B30"),
        original_start_date=date(2010, 1, 1),
    )
    make_renewal(amm, status="OBTENU", number="R2", start_date=date(2020, 1, 1))
    url = f"{URL}/pages/{amm.pk}/gaps"
    body = country_client.get(URL).json()
    page = next(p for s in body["sections"] for p in s["pages"] if p["amm_id"] == str(amm.pk))
    gap = next(e for e in page["chronology"] if e["kind"] == "gap")
    assert gap["issues"] and not gap.get("ignored")
    payload = {"start_date": gap["start_date"], "end_date": gap["end_date"]}
    body = country_client.post(url, payload, format="json").json()
    page = next(p for s in body["sections"] for p in s["pages"] if p["amm_id"] == str(amm.pk))
    gap = next(e for e in page["chronology"] if e["kind"] == "gap")
    assert gap["ignored"] is True and gap["issues"] == []
    body = country_client.post(url, {**payload, "ignored": False}, format="json").json()
    page = next(p for s in body["sections"] for p in s["pages"] if p["amm_id"] == str(amm.pk))
    assert next(e for e in page["chronology"] if e["kind"] == "gap")["issues"]
