"""Non-régression de la campagne de chaos : atomicité, concurrence, idempotence (s15, s02b).

Les tests de concurrence exigent PostgreSQL (verrous de ligne réels) : ils sont ignorés sous
SQLite et tournent en CI (DATABASE_URL_TEST).
"""

import threading
from unittest import mock

import pytest
from django.db import connection
from django.db.models.signals import post_save

from apps.amm.models import MarketingAuthorization, Renewal
from tests.conftest import client_for

needs_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql", reason="verrous de ligne : PostgreSQL requis"
)


def run_concurrently(n, fn):
    """Lance fn(i) dans n threads libérés en même temps ; chaque thread ferme sa connexion."""
    from django.db import connections

    gate = threading.Barrier(n)
    results, errors = [None] * n, []

    def target(i):
        try:
            gate.wait()
            results[i] = fn(i)
        except Exception as exc:  # pragma: no cover - remonté par l'assertion
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=target, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    return results


# --- atomicité : une modification sans trace d'audit est impossible -----------------------


@pytest.mark.django_db(transaction=True)
def test_amm_patch_is_all_or_nothing(users, make_amm):
    """Crash simulé après l'UPDATE, pendant l'écriture de l'historique : rien ne doit rester."""
    amm = make_amm(notes="avant")
    client = client_for(users["ceo"])
    history_model = MarketingAuthorization.history.model

    def boom(sender, instance, **kwargs):
        raise RuntimeError("crash entre l'UPDATE et l'historique")

    post_save.connect(boom, sender=history_model)
    client.raise_request_exception = False
    try:
        response = client.patch(f"/api/v1/amms/{amm.pk}", {"notes": "après"}, format="json")
    finally:
        post_save.disconnect(boom, sender=history_model)
    assert response.status_code == 500
    amm.refresh_from_db()
    assert amm.notes == "avant"


# --- concurrence --------------------------------------------------------------------------


@needs_postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_patches_do_not_lose_updates(users, make_amm):
    amm = make_amm(notes="n0", holder="h0")

    def edit(i):
        client = client_for(users["ceo"])
        field = "notes" if i % 2 == 0 else "holder"
        return client.patch(f"/api/v1/amms/{amm.pk}", {field: f"{field}-{i}"}, format="json")

    for round_ in range(5):
        run_concurrently(2, lambda i, r=round_: edit(2 * r + i))
        amm.refresh_from_db()
        assert amm.notes == f"notes-{2 * round_}"
        assert amm.holder == f"holder-{2 * round_ + 1}"


@needs_postgres
@pytest.mark.django_db(transaction=True)
def test_concurrent_replaces_leave_one_current_version(users, make_amm, make_scan):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.documents.models import Document
    from tests.conftest import MINIMAL_PDF

    amm = make_amm()
    original = make_scan(amm)

    def replace(i):
        client = client_for(users["ceo"])
        upload = SimpleUploadedFile(f"v{i}.pdf", MINIMAL_PDF + f"%v{i}".encode())
        return client.post(
            f"/api/v1/documents/{original.pk}/replace", {"file": upload}, format="multipart"
        ).status_code

    codes = run_concurrently(6, replace)
    current = Document.objects.filter(replaces=original, is_current=True, archived_at=None)
    assert current.count() == 1
    assert codes.count(201) == 1


@needs_postgres
@pytest.mark.django_db(transaction=True)
def test_transition_and_decision_do_not_deadlock(users, make_amm):
    """Ordre de verrouillage unique (AMM puis renouvellement) : ni interblocage ni 500."""
    amm = make_amm()
    renewal = Renewal.objects.create(
        amm=amm, workflow_status=Renewal.WorkflowStatus.DEPOSE, filing_date="2026-06-01"
    )

    def act(i):
        client = client_for(users["ceo"])
        if i % 2:
            return client.post(
                f"/api/v1/renewals/{renewal.pk}/transition", {"to": "EN_INSTRUCTION"}, format="json"
            ).status_code
        return client.post(
            f"/api/v1/amms/{amm.pk}/renewals",
            {"number": "R-1", "start_date": "2026-07-01"},
            format="json",
        ).status_code

    for _ in range(4):
        codes = run_concurrently(2, act)
        assert all(code < 500 for code in codes), codes


# --- idempotence : la même décision envoyée deux fois n'en crée qu'une -------------------


@pytest.mark.django_db
def test_same_decision_twice_creates_one_renewal(ceo_client, make_amm):
    amm = make_amm()
    payload = {"number": "SN-2026-0042", "start_date": "2026-05-01"}
    first = ceo_client.post(f"/api/v1/amms/{amm.pk}/renewals", payload, format="json")
    again = ceo_client.post(f"/api/v1/amms/{amm.pk}/renewals", payload, format="json")
    assert first.status_code == 201
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert Renewal.objects.filter(amm=amm).count() == 1


@needs_postgres
@pytest.mark.django_db(transaction=True)
def test_same_decision_sent_concurrently_creates_one_renewal(users, make_amm):
    amm = make_amm()

    def send(i):
        client = client_for(users["ceo"])
        return client.post(
            f"/api/v1/amms/{amm.pk}/renewals",
            {"number": "SN-2026-0043", "start_date": "2026-05-01"},
            format="json",
        ).status_code

    codes = run_concurrently(8, send)
    assert Renewal.objects.filter(amm=amm).count() == 1
    assert sorted(set(codes)) == [200, 201]


# --- purge : jamais de ligne pointant vers un fichier disparu -----------------------------


@pytest.mark.django_db(transaction=True)
def test_purge_never_leaves_a_row_without_its_file(make_amm, make_scan):
    from datetime import timedelta

    from django.utils import timezone

    from apps.documents.models import Document
    from apps.documents.tasks import purge_archived_documents

    amm = make_amm()
    document = make_scan(amm)
    long_ago = timezone.now() - timedelta(days=4000)
    Document.objects.filter(pk=document.pk).update(archived_at=long_ago)

    with mock.patch.object(Document, "delete", side_effect=RuntimeError("crash avant le DELETE")):
        with pytest.raises(RuntimeError):
            purge_archived_documents()
    document.refresh_from_db()
    assert document.file.storage.exists(document.file.name)


@pytest.mark.django_db
def test_malformed_renewal_id_is_a_404(ceo_client):
    response = ceo_client.patch("/api/v1/renewals/pas-un-uuid", {"notes": "x"}, format="json")
    assert response.status_code == 404
