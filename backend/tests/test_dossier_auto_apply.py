"""Validation automatique d'un dossier sûr, et projection « après validation » de l'aperçu."""

from datetime import date

import pytest

from apps.imports.dossier.application import apply_dossier, preview_token
from apps.imports.models import DossierImport
from apps.imports.tasks import analyze_dossier, can_auto_apply
from apps.notifications.models import Notification

from .test_dossier_application import new_batch, ready, stored
from .test_dossier_recognition import decision

pytestmark = pytest.mark.django_db


def analyze(batch, capture):
    with capture(execute=True):
        analyze_dossier(str(batch.pk))
    batch.refresh_from_db()
    return batch


def expired_amm_with_renewal_dossier(users, product, make_amm):
    """AMM expirée sans scan ; le dossier apporte l'origine et un renouvellement obtenu."""
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00152", start=date(2019, 4, 28)
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2019"))
    stored(
        batch,
        "AMM_PRODUIT/RENOUVELLEMENT_2026/decision.pdf",
        decision(product, start="20/08/2026", number="AMM/SN/2026/R1", renewal=True),
    )
    return amm, batch


def test_safe_dossier_is_applied_automatically_and_says_so(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    amm, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    batch = analyze(batch, django_capture_on_commit_callbacks)

    assert batch.preview["level"] == "HIGH", batch.preview
    assert batch.status == DossierImport.Status.APPLIED and batch.auto_applied
    assert batch.amm_id == amm.pk
    amm.refresh_from_db()
    assert (amm.status, amm.dossier_state) == ("VALIDE", "COMPLET")
    # Bilan et notifications habituels, avec la mention de la validation automatique.
    assert batch.summary["after"]["effective_end_date"] == "2031-08-20"
    note = Notification.objects.filter(user=users["country"]).get()
    assert "validé automatiquement" in note.body
    # L'auteur de l'import reste le validateur tracé.
    assert set(batch.audit.values_list("user", flat=True)) == {users["hq"].pk}


def test_projection_announces_what_validation_will_produce(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    amm, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    preview = ready(batch)
    projection = preview["projection"]
    assert projection["effective_end_date"] == "2031-08-20"
    assert projection["status"] == "VALIDE"
    assert projection["dossier_state"] == "COMPLET" and projection["missing_scan"] is None
    steps = projection["timeline"]
    assert [step["key"] for step in steps] == ["original", preview["renewals"][0]["key"]]
    assert steps[0]["start_date"] == "2019-04-28" and not steps[0]["in_force"]
    assert steps[1]["number"] == "AMM/SN/2026/R1" and steps[1]["in_force"]
    assert steps[1]["end_date"] == "2031-08-20"

    # Même résultat que le bilan réel après validation.
    with django_capture_on_commit_callbacks(execute=True):
        apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token, accepted_changes=[])
    after = DossierImport.objects.get(pk=batch.pk).summary["after"]
    assert after == {
        key: projection[key] for key in ("status", "dossier_state", "effective_end_date")
    }


def test_projection_names_the_missing_scan(users, product, make_amm, make_renewal):
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00152", start=date(2021, 4, 28)
    )
    make_renewal(
        amm, "OBTENU", number="R-2026", start_date=date(2026, 4, 28), end_date=date(2031, 4, 28)
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="28/04/2021"))
    projection = ready(batch)["projection"]
    assert projection["dossier_state"] == "INCOMPLET"
    assert "renouvellement n° R-2026" in projection["missing_scan"]
    # Le renouvellement déjà enregistré, absent du dossier, figure dans la chronologie.
    assert [step["number"] for step in projection["timeline"]] == ["AMM/SN/2025/00152", "R-2026"]
    assert projection["timeline"][1]["key"] is None and projection["timeline"][1]["in_force"]


def test_projection_is_outside_the_preview_token(users, product, make_amm):
    _, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    preview = ready(batch)
    assert preview_token({**preview, "projection": None}) == batch.preview_token


def test_a_correction_of_an_existing_value_is_never_applied_automatically(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    make_amm(product_obj=product, original_number="AMM/SN/2025/00125", start=date(2025, 4, 28))
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.preview["level"] == "HIGH"
    assert any(change["requires_confirmation"] for change in batch.preview["changes"])
    assert batch.status == DossierImport.Status.READY and not batch.auto_applied
    assert not Notification.objects.exists()


def test_uncertain_reading_is_left_for_review(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    make_amm(product_obj=product, original_number="AMM/SN/2025/00152", start=date(2025, 4, 28))
    batch = new_batch(users["hq"])
    record = stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    record.extraction = {**record.extraction, "source": "ocr", "confidence": 80}
    record.save()
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.preview["confidence"] < 90 and batch.preview["level"] != "HIGH"
    assert batch.status == DossierImport.Status.READY and not batch.auto_applied


def test_failed_automatic_application_leaves_the_dossier_to_review(
    users, product, make_amm, monkeypatch, django_capture_on_commit_callbacks
):
    _, batch = expired_amm_with_renewal_dossier(users, product, make_amm)

    def boom(*args, **kwargs):
        raise RuntimeError("panne")

    monkeypatch.setattr("apps.imports.dossier.application.apply_dossier", boom)
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.READY and not batch.auto_applied
    assert batch.preview["can_apply"] and batch.preview_token


def test_automatic_application_can_be_disabled(
    users, product, make_amm, settings, django_capture_on_commit_callbacks
):
    settings.DOSSIER_AUTO_APPLY = False
    _, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.READY and not batch.auto_applied


def test_auto_apply_rules():
    safe = {
        "can_apply": True,
        "blockers": [],
        "level": "HIGH",
        "confidence": 95,
        "changes": [{"requires_confirmation": False}],
        "number_warnings": [],
        "amm": {"product_id": "p"},
    }
    assert can_auto_apply(safe)
    assert not can_auto_apply({**safe, "level": "MEDIUM", "confidence": 83})
    assert not can_auto_apply({**safe, "changes": [{"requires_confirmation": True}]})
    assert not can_auto_apply({**safe, "number_warnings": ["lectures divergentes"]})
    assert not can_auto_apply({**safe, "blockers": ["x"], "can_apply": False})
    # Un produit à créer dans le catalogue reste une décision humaine.
    assert not can_auto_apply({**safe, "amm": {"product_id": None}})
