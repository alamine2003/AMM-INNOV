"""Rangement automatique dès l'AMM identifiée, et projection « après rangement » de l'aperçu."""

from datetime import date

import pytest

from apps.imports.dossier.application import apply_dossier, preview_token
from apps.imports.models import DossierImport, DossierReviewPoint
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

    assert batch.status == DossierImport.Status.APPLIED and batch.auto_applied
    assert batch.amm_id == amm.pk
    amm.refresh_from_db()
    assert (amm.status, amm.dossier_state) == ("VALIDE", "COMPLET")
    # Bilan et notifications habituels, avec la mention du rangement automatique.
    assert batch.summary["after"]["effective_end_date"] == "2031-08-20"
    note = Notification.objects.filter(user=users["country"]).get()
    assert "rangé automatiquement" in note.body
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
        apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token)
    after = DossierImport.objects.get(pk=batch.pk).summary["after"]
    keys = (
        "status",
        "dossier_state",
        "effective_end_date",
        "ideal_filing_date",
        "agency_filing_deadline",
    )
    assert after == {key: projection[key] for key in keys}


def test_projection_uses_the_same_rules_to_renew_and_filing_dates(users, product, make_amm):
    """Fin dans moins de six mois : la projection annonce « À renouveler » et ses deux dates."""
    make_amm(product_obj=product, original_number="AMM/SN/2021/00152", start=date(2021, 11, 1))
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product, start="01/11/2021"))
    projection = ready(batch)["projection"]
    assert projection["effective_end_date"] == "2026-11-01"
    assert projection["status"] == "A_RENOUVELER"
    assert projection["ideal_filing_date"] == "2026-05-01"
    assert projection["agency_filing_deadline"] == "2026-08-01"
    # Complétude indépendante de la validité : le scan de l'origine suffit.
    assert projection["dossier_state"] == "COMPLET"


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


def test_discrepancy_is_ranged_automatically_and_noted_for_later(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    """Écart scan ≠ fiche : rangé quand même, la fiche gardée, un point à vérifier plus tard."""
    amm = make_amm(
        product_obj=product, original_number="AMM/SN/2025/00125", start=date(2025, 4, 28)
    )
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.APPLIED and batch.auto_applied
    amm.refresh_from_db()
    assert amm.original_number == "AMM/SN/2025/00125"
    assert amm.dossier_state == "COMPLET"
    point = DossierReviewPoint.objects.get(amm=amm, status="OPEN")
    assert point.field == "original_number" and point.scan_value == "AMM/SN/2025/00152"
    assert batch.summary["review_points"] == 1
    note = Notification.objects.filter(user=users["country"]).get()
    assert "1 point à vérifier plus tard" in note.body


def test_uncertain_reading_is_ranged_without_threshold(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    make_amm(product_obj=product, original_number="AMM/SN/2025/00152", start=date(2025, 4, 28))
    batch = new_batch(users["hq"])
    record = stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    record.extraction = {**record.extraction, "source": "ocr", "confidence": 80}
    record.save()
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.preview["confidence"] < 90
    assert batch.status == DossierImport.Status.APPLIED and batch.auto_applied


def test_unidentifiable_amm_asks_the_question_and_writes_nothing(
    users, product, django_capture_on_commit_callbacks
):
    # Produit sans AMM au Sénégal : pas de création automatique, une question.
    batch = new_batch(users["hq"])
    stored(batch, "AMM_PRODUIT/AMM_ORIGINE/decision_amm.pdf", decision(product))
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.QUESTION and not batch.auto_applied
    assert batch.preview["question"]["codes"] == ["no_amm"]
    assert not Notification.objects.exists()
    assert not DossierReviewPoint.objects.exists()


def test_failed_automatic_application_leaves_the_dossier_ready(
    users, product, make_amm, monkeypatch, django_capture_on_commit_callbacks
):
    _, batch = expired_amm_with_renewal_dossier(users, product, make_amm)

    def boom(*args, **kwargs):
        raise RuntimeError("panne")

    monkeypatch.setattr("apps.imports.dossier.application.apply_dossier", boom)
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.READY and not batch.auto_applied
    assert batch.preview["question"] is None and batch.preview_token


def test_automatic_application_can_be_disabled(
    users, product, make_amm, settings, django_capture_on_commit_callbacks
):
    settings.DOSSIER_AUTO_APPLY = False
    _, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.READY and not batch.auto_applied


def test_auto_apply_rules():
    identified = {"question": None, "amm": {"id": "amm-1"}, "confidence": 40, "level": "LOW"}
    # Plus de seuil de fiabilité : seule l'identification de l'AMM compte.
    assert can_auto_apply(identified)
    assert not can_auto_apply({**identified, "question": {"reasons": ["Pays non reconnu."]}})
    # Une AMM à créer reste une décision humaine du siège.
    assert not can_auto_apply({**identified, "amm": {"id": None}})


def lose(record):
    """Scan perdu : déposé avant le stockage permanent (disque éphémère, 22/09/2026)."""
    record.file.storage.delete(record.file.name)


def test_lost_scan_is_taken_from_another_copy_of_the_same_file(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    amm, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    for record in batch.files.all():
        # Le même scan a été redéposé depuis dans un autre lot : son contenu sert au rangement.
        copy = stored(new_batch(users["hq"]), record.relative_path, record.extraction["text"])
        assert copy.sha256 == record.sha256
        lose(record)
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.APPLIED, batch.error
    assert amm.documents.count() == 2


def test_lost_scan_without_copy_says_to_upload_again(
    users, product, make_amm, django_capture_on_commit_callbacks, hq_client
):
    _, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    for record in batch.files.all():
        lose(record)
    batch = analyze(batch, django_capture_on_commit_callbacks)
    assert batch.status == DossierImport.Status.FAILED
    assert "redéposez ce dossier" in batch.error
    # Ranger à la main : message clair (400), plus d'erreur serveur.
    ready(batch)
    response = hq_client.post(
        f"/api/v1/dossier-imports/{batch.pk}/confirm",
        {"preview_token": batch.preview_token, "create_amm": False},
        format="json",
    )
    assert response.status_code == 400 and "redéposez" in str(response.data)


def test_dossiers_read_with_older_rules_are_reread_and_filed(
    users, product, make_amm, django_capture_on_commit_callbacks
):
    """« À ranger » depuis le 22/09 : relu avec les règles actuelles, puis rangé d'office."""
    from apps.core.tasks import reread_stale_dossiers

    amm, batch = expired_amm_with_renewal_dossier(users, product, make_amm)
    preview = ready(batch)
    DossierImport.objects.filter(pk=batch.pk).update(preview={**preview, "version": 2})
    with django_capture_on_commit_callbacks(execute=True):
        assert reread_stale_dossiers() == 1
    batch.refresh_from_db()
    assert batch.status == DossierImport.Status.APPLIED and batch.amm_id == amm.pk
    assert reread_stale_dossiers() == 0
