"""Rubrique « Dépôt AMM » : montage au siège, envoi au pays, dépôt, commission, décision."""

import io
import zipfile
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.amm.models import Renewal
from apps.deposits.models import DepositDossier, PieceType
from apps.documents.models import Document
from apps.notifications.models import Notification
from tests.conftest import MINIMAL_PDF, TODAY


def pdf(name="piece.pdf", salt=b""):
    return SimpleUploadedFile(name, MINIMAL_PDF + salt, content_type="application/pdf")


def docx(name="lettre.docx"):
    return SimpleUploadedFile(name, b"PK\x03\x04 lettre", content_type="application/msword")


@pytest.fixture
def amm(make_amm):
    return make_amm("SN", start=TODAY - timedelta(days=5 * 365 - 100))


@pytest.fixture
def dossier(hq_client, amm):
    response = hq_client.post("/api/v1/deposits", {"amm": str(amm.pk)}, format="json")
    assert response.status_code == 201, response.content
    return response.json()


def fill(client, dossier, with_samples=True):
    for item in dossier["checklist"]:
        if item["piece_type"]["required"]:
            upload = (
                docx()
                if "Lettre" in item["piece_type"]["label"]
                else pdf(salt=item["piece_type"]["id"].encode())
            )
            response = client.post(
                f"/api/v1/deposits/{dossier['id']}/pieces",
                {"file": upload, "piece_type": item["piece_type"]["id"]},
                format="multipart",
            )
            assert response.status_code == 201, response.content
    if with_samples:
        response = client.post(
            f"/api/v1/deposits/{dossier['id']}/samples",
            {
                "batch_number": "L2409",
                "manufactured_on": "2026-03-01",
                "expires_on": "2029-02-28",
                "quantity": 3,
            },
            format="json",
        )
        assert response.status_code == 201, response.content
    return response.json()


def test_open_dossier_plans_and_prepares_the_renewal(dossier, amm):
    renewal = amm.renewals.get()
    assert renewal.workflow_status == Renewal.WorkflowStatus.EN_PREPARATION
    assert dossier["stage"] == "MONTAGE"
    labels = [item["piece_type"]["label"] for item in dossier["checklist"]]
    assert labels[:2] == ["Lettre de demande de renouvellement", "Certificat de PGHT"]
    assert dossier["pieces_required"] == 5 and dossier["pieces_done"] == 0
    assert "Échantillons" in dossier["missing"][-1]


def test_only_hq_opens_and_one_dossier_per_renewal(country_client, hq_client, dossier, amm):
    assert (
        country_client.post("/api/v1/deposits", {"amm": str(amm.pk)}, format="json").status_code
        == 403
    )
    again = hq_client.post("/api/v1/deposits", {"amm": str(amm.pk)}, format="json")
    assert again.status_code == 400
    assert "déjà ouvert" in str(again.json())


def test_country_pieces_adjustments(countries, hq_client, amm):
    base = PieceType.objects.get(label="Certificat de PGHT")
    base.excluded_countries.add(countries["SN"])
    PieceType.objects.create(label="Quittance de paiement", country=countries["SN"], order=5)
    PieceType.objects.create(label="Visa du Mali", country=countries["ML"])
    dossier = hq_client.post("/api/v1/deposits", {"amm": str(amm.pk)}, format="json").json()
    labels = [item["piece_type"]["label"] for item in dossier["checklist"]]
    assert "Certificat de PGHT" not in labels
    assert "Quittance de paiement" in labels
    assert "Visa du Mali" not in labels


def test_send_refused_until_complete_then_country_is_notified(hq_client, users, dossier):
    refused = hq_client.post(f"/api/v1/deposits/{dossier['id']}/send", {}, format="json")
    assert refused.status_code == 400
    assert "Dossier incomplet" in str(refused.json())
    detail = fill(hq_client, dossier)
    assert detail["missing"] == []
    sent = hq_client.post(
        f"/api/v1/deposits/{dossier['id']}/send",
        {"note": "Échantillons partis par DHL"},
        format="json",
    )
    assert sent.status_code == 200
    assert sent.json()["stage"] == "ENVOYE"
    note = Notification.objects.get(user=users["country"])
    assert note.title.startswith("Dossier de renouvellement à déposer")
    assert note.link.endswith(f"/depots/{dossier['id']}")
    assert "DHL" in note.body


def test_country_downloads_the_zip_once_sent(hq_client, country_client, users, dossier):
    fill(hq_client, dossier)
    assert country_client.get(f"/api/v1/deposits/{dossier['id']}/archive").status_code == 403
    hq_client.post(f"/api/v1/deposits/{dossier['id']}/send", {}, format="json")
    response = country_client.get(f"/api/v1/deposits/{dossier['id']}/archive")
    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))
    names = archive.namelist()
    assert names[0] == "00 - Bordereau du dossier.pdf"
    assert "01 - Lettre de demande de renouvellement/lettre.docx" in names
    assert archive.read(names[0]).startswith(b"%PDF")
    detail = country_client.get(f"/api/v1/deposits/{dossier['id']}").json()
    assert detail["downloads"][0]["user"] == "Fatou"
    assert Notification.objects.filter(
        user=users["hq"], title__startswith="Dossier téléchargé"
    ).exists()


def test_deposit_commission_decision(hq_client, country_client, users, dossier, amm):
    fill(hq_client, dossier)
    hq_client.post(f"/api/v1/deposits/{dossier['id']}/send", {}, format="json")
    url = f"/api/v1/deposits/{dossier['id']}"
    deposited = country_client.post(
        f"{url}/deposit",
        {"filing_date": "2026-09-01", "file": pdf("attestation.pdf", b"att")},
        format="multipart",
    )
    assert deposited.status_code == 200, deposited.content
    body = deposited.json()
    assert body["stage"] == "DEPOSE"
    assert body["renewal"]["filing_date"] == "2026-09-01"
    attestation = Document.objects.get(pk=body["attestation"]["id"])
    assert (
        attestation.kind == Document.Kind.RECEPISSE
        and str(attestation.renewal_id) == body["renewal"]["id"]
    )
    assert Notification.objects.filter(
        user=users["hq"], title__startswith="Attestation de dépôt reçue"
    ).exists()

    commission = country_client.post(
        f"{url}/events",
        {"kind": "COMMISSION", "date": "2026-09-03", "note": "Examen en séance"},
        format="multipart",
    )
    assert commission.status_code == 201
    assert commission.json()["stage"] == "COMMISSION"
    assert amm.renewals.get().workflow_status == Renewal.WorkflowStatus.EN_INSTRUCTION

    decision = country_client.post(
        f"{url}/decision",
        {
            "result": "OBTENU",
            "decision_date": "2026-09-04",
            "number": "AMM/SN/2026/001-R",
            "start_date": "2026-09-04",
            "file": pdf("decision.pdf", b"dec"),
        },
        format="multipart",
    )
    assert decision.status_code == 200, decision.content
    assert decision.json()["stage"] == "OBTENU"
    renewal = amm.renewals.get()
    assert renewal.number == "AMM/SN/2026/001-R" and renewal.end_date is not None
    amm.refresh_from_db()
    assert amm.effective_end_date == renewal.end_date
    assert Document.objects.filter(renewal=renewal, kind=Document.Kind.AMM).exists()
    assert decision.json()["can"]["manage"] is False


def test_rejection_from_deposit_goes_through_instruction(hq_client, dossier, amm):
    url = f"/api/v1/deposits/{dossier['id']}"
    hq_client.post(
        f"{url}/deposit", {"filing_date": "2026-09-01", "file": pdf(salt=b"a")}, format="multipart"
    )
    rejected = hq_client.post(
        f"{url}/decision", {"result": "REJETE", "decision_date": "2026-09-04"}, format="multipart"
    )
    assert rejected.status_code == 200, rejected.content
    assert rejected.json()["stage"] == "REJETE"


def test_messages_notify_the_other_side(hq_client, country_client, users, dossier):
    url = f"/api/v1/deposits/{dossier['id']}/messages"
    assert (
        country_client.post(
            url, {"body": "Le formulaire a changé cette année."}, format="json"
        ).status_code
        == 201
    )
    assert Notification.objects.filter(user=users["hq"], body__contains="formulaire").exists()
    answer = hq_client.post(url, {"body": "Je l'ajoute."}, format="json").json()
    assert [m["from_hq"] for m in answer["messages"]] == [False, True]
    assert Notification.objects.filter(user=users["country"], body="Je l'ajoute.").exists()


def test_country_scope_and_hq_only_actions(make_amm, hq_client, country_client, dossier):
    other = make_amm("CI")
    hidden = hq_client.post("/api/v1/deposits", {"amm": str(other.pk)}, format="json").json()
    assert country_client.get(f"/api/v1/deposits/{hidden['id']}").status_code == 404
    listed = [row["id"] for row in country_client.get("/api/v1/deposits").json()]
    assert listed == [dossier["id"]]
    piece_type = dossier["checklist"][0]["piece_type"]["id"]
    refused = country_client.post(
        f"/api/v1/deposits/{dossier['id']}/pieces",
        {"file": pdf(), "piece_type": piece_type},
        format="multipart",
    )
    assert refused.status_code == 403


def test_piece_validation_and_samples(hq_client, dossier):
    url = f"/api/v1/deposits/{dossier['id']}"
    bad = hq_client.post(
        f"{url}/pieces",
        {"file": SimpleUploadedFile("virus.exe", b"MZ"), "label": "Autre"},
        format="multipart",
    )
    assert bad.status_code == 400 and "Format non accepté" in str(bad.json())
    dates = hq_client.post(
        f"{url}/samples",
        {"batch_number": "L1", "manufactured_on": "2026-03-01", "expires_on": "2025-01-01"},
        format="json",
    )
    assert dates.status_code == 400
    other = hq_client.post(
        f"{url}/pieces", {"file": pdf(salt=b"o"), "label": "Procuration"}, format="multipart"
    )
    assert other.json()["other_pieces"][0]["label"] == "Procuration"
    hq_client.post(f"{url}/samples-required", {"required": False}, format="json")
    assert not any("Échantillons" in item for item in hq_client.get(url).json()["missing"])


def test_suggestions_list_amms_to_renew_without_dossier(
    make_amm, hq_client, country_client, dossier, amm
):
    soon = make_amm("SN", start=TODAY - timedelta(days=5 * 365 - 30))
    later = make_amm("SN", start=TODAY - timedelta(days=365))
    long_expired = make_amm("SN", start=TODAY - timedelta(days=8 * 365))
    ids = [row["id"] for row in hq_client.get("/api/v1/deposits/suggestions").json()]
    assert str(soon.pk) in ids
    assert str(amm.pk) not in ids  # dossier déjà ouvert
    assert str(later.pk) not in ids  # échéance dans plus d'un an
    assert str(long_expired.pk) not in ids  # expirée depuis des années : nouvelle demande


def test_renewal_concluded_elsewhere_closes_the_dossier(hq_client, dossier, amm):
    renewal = amm.renewals.get()
    Renewal.objects.filter(pk=renewal.pk).update(workflow_status=Renewal.WorkflowStatus.ABANDONNE)
    assert DepositDossier.objects.get(pk=dossier["id"]).stage == "ABANDONNE"
    closed = hq_client.post(f"/api/v1/deposits/{dossier['id']}/send", {}, format="json")
    assert closed.status_code == 400


def test_piece_types_are_managed_by_hq(hq_client, country_client, countries):
    created = hq_client.post(
        "/api/v1/deposit-pieces",
        {"label": "Quittance", "country": "SN", "required": True, "order": 70},
        format="json",
    )
    assert created.status_code == 201
    assert (
        country_client.post("/api/v1/deposit-pieces", {"label": "X"}, format="json").status_code
        == 403
    )
    patched = hq_client.patch(
        f"/api/v1/deposit-pieces/{PieceType.objects.get(label='RCP').pk}",
        {"excluded_countries": ["ML"]},
        format="json",
    )
    assert patched.json()["excluded_countries"] == ["ML"]
    assert len(country_client.get("/api/v1/deposit-pieces").json()) == 7
