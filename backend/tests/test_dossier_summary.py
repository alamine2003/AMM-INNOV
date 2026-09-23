"""Bilan d'un import de dossier validé : avant/après, renouvellements, documents, notifications."""

from datetime import date

import pytest

from apps.accounts.models import User
from apps.imports.dossier.application import apply_dossier
from apps.imports.models import DossierImport
from apps.notifications.models import Notification

from .test_dossier_application import new_batch, ready, stored
from .test_dossier_recognition import decision

pytestmark = pytest.mark.django_db


def test_summary_and_notifications_after_a_renewal(
    users, product, make_amm, countries, django_capture_on_commit_callbacks
):
    # AMM expirée, sans scan : le dossier apporte la décision d'origine et un renouvellement.
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00152", start=date(2019, 4, 28)
    )
    amm.refresh_from_db()
    assert (amm.status, amm.dossier_state) == ("EXPIRE", "INCOMPLET")
    outsider = User.objects.create_user(
        "ml@test.local", "Passw0rd!", role=User.Role.COUNTRY_REGULATORY
    )
    outsider.countries.set([countries["ML"]])

    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2019"))
    stored(
        batch,
        "AMM_PRODUIT/RENOUVELLEMENT_2026/decision.pdf",
        decision(product, start="20/08/2026", number="AMM/SN/2026/R1", renewal=True),
    )
    preview = ready(batch)
    assert preview["can_apply"], preview["blockers"]
    with django_capture_on_commit_callbacks(execute=True):
        apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token)

    batch.refresh_from_db()
    s = batch.summary
    assert s["amm_id"] == str(amm.pk) and not s["created"]
    assert s["before"]["status"] == "EXPIRE" and s["before"]["dossier_state"] == "INCOMPLET"
    assert s["after"]["status"] == "VALIDE" and s["after"]["dossier_state"] == "COMPLET"
    assert s["after"]["effective_end_date"] == "2031-08-20"
    assert s["renewals_created"] == [
        {"number": "AMM/SN/2026/R1", "start_date": "2026-08-20", "end_date": "2031-08-20"}
    ]
    assert len(s["documents"]) == 2 and s["missing_scan"] is None
    assert "Statut : Expirée → Valide" in s["lines"]
    assert "Dossier : Dossier incomplet → Dossier complet" in s["lines"]

    # Auteur (siège), CEO et réglementaire SN prévenus ; le réglementaire Mali ne l'est pas.
    notified = set(Notification.objects.values_list("user__email", flat=True))
    assert notified == {"hq@test.local", "ceo@test.local", "sn@test.local"}
    note = Notification.objects.filter(user=users["country"]).get()
    assert note.channel == "IN_APP" and note.link.endswith(f"/dossier-imports/{batch.pk}")
    assert product.name in note.title and "Expirée → Valide" in note.title
    assert "Renouvellement n° AMM/SN/2026/R1 ajouté" in note.body


def test_scan_of_an_outdated_decision_says_what_is_missing(
    users, product, make_amm, make_renewal, django_capture_on_commit_callbacks
):
    # Un renouvellement obtenu sans scan fait foi : le scan d'origine ne suffit pas.
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00152", start=date(2021, 4, 28)
    )
    make_renewal(
        amm, "OBTENU", number="R-2026", start_date=date(2026, 4, 28), end_date=date(2031, 4, 28)
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2021"))
    preview = ready(batch)
    assert preview["can_apply"], preview["blockers"]
    with django_capture_on_commit_callbacks(execute=True):
        apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token)

    s = DossierImport.objects.get(pk=batch.pk).summary
    assert s["after"]["dossier_state"] == "INCOMPLET"
    assert "renouvellement n° R-2026" in s["missing_scan"]
    assert any(line.startswith("Dossier toujours incomplet") for line in s["lines"])


def test_summary_failure_never_breaks_the_import(
    users, product, make_amm, monkeypatch, django_capture_on_commit_callbacks
):
    make_amm(product_obj=product, original_number="AMM/SN/2025/00152", start=date(2025, 4, 28))
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    ready(batch)

    def boom(*args, **kwargs):
        raise RuntimeError("panne")

    monkeypatch.setattr("apps.imports.dossier.summary.build_summary", boom)
    with django_capture_on_commit_callbacks(execute=True):
        applied = apply_dossier(
            batch.pk, user=users["hq"], token=batch.preview_token
        )
    assert applied.status == DossierImport.Status.APPLIED
    assert DossierImport.objects.get(pk=batch.pk).summary == {}
