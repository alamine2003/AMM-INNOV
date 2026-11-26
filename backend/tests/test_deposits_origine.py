"""1.4.1 : dossier de dépôt d'une AMM d'origine, et annulation d'un dossier de dépôt."""

from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services.gaps import with_gaps
from apps.catalog.models import Product
from apps.core.models import TrashEntry
from apps.core.trash import restore
from apps.deposits.models import DepositDossier, DepositPiece
from apps.documents.models import Document
from apps.notifications.models import Notification
from tests.conftest import MINIMAL_PDF, TODAY

APP = MarketingAuthorization.OriginApplication
W = Renewal.WorkflowStatus


def pdf(name="piece.pdf", salt=b""):
    return SimpleUploadedFile(name, MINIMAL_PDF + salt, content_type="application/pdf")


@pytest.fixture
def new_product(ranges):
    return Product.objects.create(name="BETAGEN 10MG CPR B/30", range=ranges["GENERALE"])


def open_origin(client, product, country="SN", **extra):
    return client.post(
        "/api/v1/deposits",
        {"kind": "ORIGINE", "product": str(product.pk), "country": country, **extra},
        format="json",
    )


@pytest.fixture
def origin(hq_client, new_product):
    response = open_origin(hq_client, new_product, holder="GHPL")
    assert response.status_code == 201, response.content
    return response.json()


def url(dossier, action=""):
    return f"/api/v1/deposits/{dossier['id']}" + (f"/{action}" if action else "")


def deposit(client, dossier, when="2026-09-01"):
    response = client.post(
        url(dossier, "deposit"),
        {"filing_date": when, "file": pdf("recepisse.pdf", when.encode())},
        format="multipart",
    )
    assert response.status_code == 200, response.content
    return response.json()


# --- Demande d'AMM d'origine ------------------------------------------------------------------


def test_opening_an_origin_application_creates_the_amm_without_number_nor_dates(
    origin, new_product, countries
):
    amm = MarketingAuthorization.objects.get(product=new_product, country=countries["SN"])
    assert origin["kind"] == "ORIGINE"
    assert origin["renewal"] is None
    assert origin["stage"] == "MONTAGE"
    assert origin["amm"]["id"] == str(amm.pk)
    assert origin["amm"]["origin_application"] == "EN_PREPARATION"
    assert amm.original_number == "" and amm.original_start_date is None
    assert amm.holder == "GHPL"
    assert amm.renewals.count() == 0
    assert amm.history.first().history_change_reason.startswith("Demande d'AMM d'origine")


def test_a_pending_origin_is_not_a_missing_origin(origin, make_amm):
    """L'origine non identifiée reste un manque pour une fiche ordinaire, pas pour une demande."""
    plain = make_amm("SN", original_number="", start=None)
    plain.original_start_date = None
    plain.save()
    flagged = set(with_gaps(MarketingAuthorization.objects.all(), ["no_original", "original_scan"]))
    assert plain in flagged
    assert str(origin["amm"]["id"]) not in {str(amm.pk) for amm in flagged}


def test_origin_application_goes_from_deposit_to_decision(hq_client, users, origin):
    sent = hq_client.post(url(origin, "samples-required"), {"required": False}, format="json")
    assert sent.status_code == 200
    filed = deposit(hq_client, origin)
    assert filed["stage"] == "DEPOSE"
    assert filed["filing_date"] == "2026-09-01"
    amm = MarketingAuthorization.objects.get(pk=origin["amm"]["id"])
    assert amm.origin_application == APP.DEPOSE
    assert amm.origin_filing_date == date(2026, 9, 1)
    receipt = Document.objects.get(amm=amm, kind=Document.Kind.RECEPISSE)
    assert receipt.renewal_id is None  # rangé avec l'AMM d'origine

    commission = hq_client.post(
        url(origin, "events"), {"kind": "COMMISSION", "date": "2026-09-03"}, format="multipart"
    )
    assert commission.json()["stage"] == "COMMISSION"
    amm.refresh_from_db()
    assert amm.origin_application == APP.EN_INSTRUCTION

    decision = hq_client.post(
        url(origin, "decision"),
        {
            "result": "OBTENU",
            "decision_date": "2026-09-10",
            "number": "AMM/SN/2026/0099",
            "start_date": "2026-09-10",
            "file": pdf("decision.pdf", b"dec"),
        },
        format="multipart",
    )
    assert decision.status_code == 200, decision.content
    body = decision.json()
    assert body["stage"] == "OBTENU" and body["stage_label"] == "AMM obtenue"
    assert body["can"]["manage"] is False and body["can"]["cancel"] is False
    amm.refresh_from_db()
    # La fiche devient une AMM comme les autres : n°, dates, échéance, statut, scan.
    assert amm.origin_application == ""
    assert amm.original_number == "AMM/SN/2026/0099"
    assert amm.original_start_date == date(2026, 9, 10)
    assert amm.original_end_date == date(2031, 9, 10)
    assert amm.status == MarketingAuthorization.Status.VALIDE
    assert amm.dossier_state == MarketingAuthorization.DossierState.COMPLET
    assert Document.objects.filter(amm=amm, kind=Document.Kind.AMM, renewal=None).exists()
    assert amm.renewals.count() == 0
    assert Notification.objects.filter(
        user=users["country"], title__startswith="AMM d'origine obtenue"
    ).exists()
    # Le renouvellement se monte ensuite comme pour toute AMM.
    renewal = hq_client.post("/api/v1/deposits", {"amm": str(amm.pk)}, format="json")
    assert renewal.status_code == 201
    assert renewal.json()["kind"] == "RENOUVELLEMENT"


def test_origin_rejection_and_a_new_application_on_the_same_amm(hq_client, origin, new_product):
    deposit(hq_client, origin)
    rejected = hq_client.post(
        url(origin, "decision"), {"result": "REJETE", "decision_date": "2026-09-04"}
    )
    assert rejected.json()["stage"] == "REJETE"
    amm = MarketingAuthorization.objects.get(pk=origin["amm"]["id"])
    assert amm.origin_application == APP.REJETE
    # Nouvelle demande : la même fiche est reprise, l'ancien dossier reste clos.
    again = open_origin(hq_client, new_product)
    assert again.status_code == 201, again.content
    assert again.json()["amm"]["id"] == str(amm.pk)
    assert hq_client.get(url(origin)).json()["stage"] == "REJETE"
    amm.refresh_from_db()
    assert amm.origin_application == APP.EN_PREPARATION


def test_origin_refused_when_the_product_already_has_an_amm_or_a_pending_application(
    hq_client, country_client, make_amm, origin, new_product
):
    existing = make_amm("SN")
    refused = open_origin(hq_client, existing.product)
    assert refused.status_code == 400
    assert "déjà une AMM" in str(refused.json())
    twice = open_origin(hq_client, new_product)
    assert twice.status_code == 400
    assert "déjà en cours" in str(twice.json())
    assert open_origin(country_client, new_product, country="ML").status_code == 403
    # Pas de renouvellement pour une AMM pas encore délivrée.
    renewal = hq_client.post("/api/v1/deposits", {"amm": origin["amm"]["id"]}, format="json")
    assert renewal.status_code == 400
    assert "demande d'AMM d'origine est en cours" in str(renewal.json())


def test_origin_abandon_keeps_the_amm_marked(hq_client, origin):
    abandoned = hq_client.post(url(origin, "abandon"), {"reason": "Produit retiré"}, format="json")
    assert abandoned.json()["stage"] == "ABANDONNE"
    amm = MarketingAuthorization.objects.get(pk=origin["amm"]["id"])
    assert amm.origin_application == APP.ABANDONNE


def test_the_zip_and_the_country_message_say_it_is_an_application(hq_client, users, origin):
    hq_client.post(url(origin, "samples-required"), {"required": False}, format="json")
    detail = hq_client.get(url(origin)).json()
    for item in detail["checklist"]:
        if item["piece_type"]["required"]:
            hq_client.post(
                url(origin, "pieces"),
                {
                    "file": pdf(salt=item["piece_type"]["id"].encode()),
                    "piece_type": item["piece_type"]["id"],
                },
                format="multipart",
            )
    sent = hq_client.post(url(origin, "send"), {}, format="json")
    assert sent.status_code == 200, sent.content
    note = Notification.objects.get(user=users["country"])
    assert note.title.startswith("Dossier de demande d'AMM à déposer")
    archive = hq_client.get(url(origin, "archive"))
    assert archive.status_code == 200


# --- Fiche AMM et classeur --------------------------------------------------------------------


def test_amm_detail_shows_the_application_and_its_dossier(hq_client, origin):
    body = hq_client.get(f"/api/v1/amms/{origin['amm']['id']}").json()
    assert body["origin_application"] == "EN_PREPARATION"
    assert body["origin_deposit_id"] == origin["id"]
    # Elle ne se saisit pas à la main.
    hq_client.patch(
        f"/api/v1/amms/{origin['amm']['id']}", {"origin_application": ""}, format="json"
    )
    assert MarketingAuthorization.objects.get(pk=origin["amm"]["id"]).origin_application


def test_binder_page_of_a_pending_application_can_be_conforme(hq_client, origin):
    deposit(hq_client, origin)
    binder = "/api/v1/binders/SN-generale-a-k"
    page = next(
        p
        for section in hq_client.get(binder).json()["sections"]
        for p in section["pages"]
        if p["amm_id"] == origin["amm"]["id"]
    )
    assert page["origin_application"] == "DEPOSE"
    assert page["status_label"] == "Demande d'origine déposée"
    origin_entry = next(e for e in page["chronology"] if e["label"] == "Demande d'AMM d'origine")
    assert origin_entry["kind"] == "pending"
    assert origin_entry["issues"] == []  # le récépissé est là, rien d'autre n'est attendu
    assert origin_entry["filing_date"] == "2026-09-01"

    checked = hq_client.post(
        f"{binder}/check", {"amm": origin["amm"]["id"], "result": "CONFORME"}, format="json"
    )
    assert checked.status_code == 200, checked.content
    page = next(
        p
        for section in checked.json()["sections"]
        for p in section["pages"]
        if p["amm_id"] == origin["amm"]["id"]
    )
    assert page["conformity"]["status"] == "CONFORME"
    details = {c["key"]: c for c in page["conformity"]["criteria"]}
    assert details["scan"]["ok"] is True and "pas encore de décision" in details["scan"]["detail"]
    assert details["data"]["detail"] == "Demande d'origine déposée le 01/09/2026"
    assert page["conformity"]["to_scan"] is False


# --- Annuler un dossier -----------------------------------------------------------------------


@pytest.fixture
def amm(make_amm):
    return make_amm("SN", start=TODAY - timedelta(days=5 * 365 - 100))


def test_cancel_a_renewal_dossier_as_if_never_opened(hq_client, users, amm):
    before = (amm.status, amm.effective_end_date)
    dossier = hq_client.post("/api/v1/deposits", {"amm": str(amm.pk)}, format="json").json()
    hq_client.post(url(dossier, "pieces"), {"file": pdf()}, format="multipart")
    deposit(hq_client, dossier)
    assert amm.renewals.count() == 1

    cancelled = hq_client.post(url(dossier, "cancel"), {"reason": "Mauvais produit"})
    assert cancelled.status_code == 204, cancelled.content
    assert not DepositDossier.objects.exists()
    assert not DepositPiece.objects.exists()
    assert amm.renewals.count() == 0  # le renouvellement planifié par le dossier est retiré
    assert not Document.objects.filter(amm=amm, kind=Document.Kind.RECEPISSE).exists()
    amm.refresh_from_db()
    assert (amm.status, amm.effective_end_date) == before
    note = Notification.objects.get(user=users["country"], title__contains="annulé")
    assert "Mauvais produit" in note.body and note.link.endswith("/depots")
    # À la corbeille, pas effacé.
    entries = TrashEntry.objects.filter(reason__startswith="Dossier de dépôt annulé")
    assert entries.count() == 2  # l'attestation, puis le renouvellement avec son dossier
    assert hq_client.get(url(dossier)).status_code == 404


def test_cancel_restores_a_renewal_that_existed_before_the_dossier(hq_client, amm):
    planned = Renewal.objects.create(amm=amm, workflow_status=W.PLANIFIE)
    dossier = hq_client.post("/api/v1/deposits", {"amm": str(amm.pk)}, format="json").json()
    planned.refresh_from_db()
    assert planned.workflow_status == W.EN_PREPARATION
    deposit(hq_client, dossier)

    assert hq_client.post(url(dossier, "cancel"), {}).status_code == 204
    planned.refresh_from_db()
    assert planned.workflow_status == W.PLANIFIE
    assert planned.filing_date is None
    assert not DepositDossier.objects.exists()


def test_cancel_an_origin_application_removes_the_amm_it_created(hq_client, origin, new_product):
    assert hq_client.post(url(origin, "cancel"), {"reason": "Erreur de pays"}).status_code == 204
    assert not MarketingAuthorization.objects.filter(product=new_product).exists()
    assert not DepositDossier.objects.exists()
    entry = TrashEntry.objects.get(object_id=origin["amm"]["id"])
    restore(entry)
    assert MarketingAuthorization.objects.filter(product=new_product).exists()
    assert DepositDossier.objects.filter(pk=origin["id"]).exists()


def test_cancel_an_origin_application_keeps_an_amm_that_existed_before(
    hq_client, origin, new_product
):
    deposit(hq_client, origin)
    hq_client.post(url(origin, "decision"), {"result": "REJETE", "decision_date": "2026-09-04"})
    again = open_origin(hq_client, new_product).json()
    assert hq_client.post(url(again, "cancel"), {}).status_code == 204
    amm = MarketingAuthorization.objects.get(product=new_product)
    assert amm.origin_application == APP.REJETE  # l'état d'avant ce dossier
    assert DepositDossier.objects.filter(pk=origin["id"]).exists()


def test_only_hq_cancels_and_only_an_open_dossier(hq_client, country_client, origin):
    assert country_client.post(url(origin, "cancel"), {}).status_code == 403
    hq_client.post(url(origin, "abandon"), {"reason": "Produit retiré"}, format="json")
    closed = hq_client.post(url(origin, "cancel"), {})
    assert closed.status_code == 400
    assert "clos" in str(closed.json())
    assert hq_client.get(url(origin)).json()["can"]["cancel"] is False


# --- Reprise des dossiers existants (migration) -----------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_migration_fills_the_amm_and_what_cancelling_would_undo():
    """Les dossiers d'avant la 1.4.1 reçoivent leur AMM ; un renouvellement créé avec le dossier
    est marqué comme tel, sinon son état d'avant le dossier est repris de son historique."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.utils import timezone

    before = [("deposits", "0002_pieces_de_base"), ("amm", "0005_index_recherche_et_suivi")]
    after = [("deposits", "0003_dossier_origine_et_annulation"), ("amm", "0006_demande_origine")]
    executor = MigrationExecutor(connection)
    executor.migrate(before)
    old = executor.loader.project_state(before).apps
    country = old.get_model("catalog", "Country").objects.create(iso2="SN", name="Sénégal")
    product_model = old.get_model("catalog", "Product")
    amm_model = old.get_model("amm", "MarketingAuthorization")
    renewal_model = old.get_model("amm", "Renewal")
    dossier_model = old.get_model("deposits", "DepositDossier")
    history = old.get_model("amm", "HistoricalRenewal")
    now = timezone.now()
    dossiers = {}
    for name, created_together in (("A", True), ("B", False)):
        amm = amm_model.objects.create(
            product=product_model.objects.create(name=f"PRODUIT {name}"), country=country
        )
        renewal = renewal_model.objects.create(
            amm=amm, sequence=1, workflow_status="EN_PREPARATION"
        )
        dossier = dossier_model.objects.create(renewal=renewal)
        if not created_together:
            renewal_model.objects.filter(pk=renewal.pk).update(created_at=now - timedelta(days=30))
            history.objects.create(
                id=renewal.pk,
                amm_id=amm.pk,
                sequence=1,
                workflow_status="PLANIFIE",
                created_at=now - timedelta(days=30),
                updated_at=now - timedelta(days=30),
                history_date=now - timedelta(days=30),
                history_type="+",
            )
        dossiers[name] = (dossier.pk, amm.pk)

    executor = MigrationExecutor(connection)
    executor.migrate(after)
    new = executor.loader.project_state(after).apps.get_model("deposits", "DepositDossier")
    a = new.objects.get(pk=dossiers["A"][0])
    b = new.objects.get(pk=dossiers["B"][0])
    assert (a.amm_id, a.kind, a.created_target, a.status_before) == (
        dossiers["A"][1],
        "RENOUVELLEMENT",
        True,
        "",
    )
    assert (b.amm_id, b.created_target, b.status_before) == (dossiers["B"][1], False, "PLANIFIE")
    executor.loader.build_graph()
    executor.migrate(executor.loader.graph.leaf_nodes())
