import logging
from datetime import date

from celery import shared_task
from django.utils import timezone

from .models import ImportBatch
from .services import import_workbook

logger = logging.getLogger(__name__)


@shared_task(name="apps.imports.tasks.run_import")
def run_import(batch_id: str, today: str | None = None) -> dict:
    # Prise en charge exclusive : la tâche peut être redistribuée (acks tardifs) ou republiée.
    claimed = ImportBatch.objects.filter(pk=batch_id, status=ImportBatch.Status.PENDING).update(
        status=ImportBatch.Status.RUNNING
    )
    if not claimed:
        return {"status": "skipped"}
    batch = ImportBatch.objects.get(pk=batch_id)
    reference = date.fromisoformat(today) if today else batch.reference_date
    batch.file.open("rb")
    try:
        summary = import_workbook(batch.file, batch=batch, today=reference, dry_run=batch.dry_run)
    finally:
        batch.file.close()
    return summary.get("totals", {})


@shared_task(name="apps.imports.tasks.analyze_dossier", soft_time_limit=1200, time_limit=1260)
def analyze_dossier(batch_id: str) -> dict:
    from .dossier.application import preview_token
    from .dossier.preview import build_preview
    from .models import DossierImport

    claimed = DossierImport.objects.filter(pk=batch_id, status=DossierImport.Status.PENDING).update(
        status=DossierImport.Status.RUNNING,
        error="",
        started_at=timezone.now(),
    )
    if not claimed:
        return {"status": "skipped"}
    batch = DossierImport.objects.select_related("created_by").get(pk=batch_id)
    try:
        if not batch.created_by or not batch.created_by.is_active:
            raise ValueError("Utilisateur indisponible")
        # Relance après un délai OCR dépassé : on refait l'extraction des seuls fichiers
        # interrompus (jamais pendant la validation, qui relit l'extraction enregistrée).
        from .dossier.extraction import extract_file, needs_retry

        for upload in batch.files.all():
            if upload.extraction and needs_retry(upload.extraction):
                upload.extraction = extract_file(upload)
                upload.save(update_fields=["extraction"])
        preview = build_preview(batch)
        # Un pays reconnu hors du périmètre de l'auteur n'est pas enregistré sur le lot :
        # sinon le lot disparaît de sa liste (404) et il ne voit jamais la question posée.
        country_id = preview.get("amm", {}).get("country_id")
        if country_id and not batch.created_by.can_access_country(country_id):
            country_id = batch.country_id
        token = preview_token(preview)
        # AMM non identifiable : une seule question, « c'est quelle AMM ? ». Sinon, prêt à ranger.
        status = (
            DossierImport.Status.QUESTION if preview["question"] else DossierImport.Status.READY
        )
        saved = DossierImport.objects.filter(
            pk=batch_id, status=DossierImport.Status.RUNNING
        ).update(
            status=status,
            preview=preview,
            preview_token=token,
            country_id=country_id,
            finished_at=timezone.now(),
        )
    except Exception:
        logger.exception("Échec de l'analyse du dossier %s", batch_id)
        DossierImport.objects.filter(pk=batch_id, status=DossierImport.Status.RUNNING).update(
            status=DossierImport.Status.FAILED,
            finished_at=timezone.now(),
            error="L'analyse a échoué. Vérifiez les documents puis relancez l'analyse.",
        )
        return {"status": "failed"}
    if saved and can_auto_apply(preview) and _auto_apply(batch, token):
        return {"status": "applied", "auto": True, "points": len(preview["review_points"])}
    return {"status": status.lower()}


def can_auto_apply(preview: dict) -> bool:
    """Rangement automatique dès que l'AMM cible est identifiée sans ambiguïté.

    Plus de seuil de fiabilité : les écarts avec la fiche et les lectures douteuses deviennent des
    points à vérifier plus tard, jamais un blocage. Seule une AMM non identifiable (question
    posée) attend le réglementaire. Aucune AMM n'est créée automatiquement.
    Désactivable par DOSSIER_AUTO_APPLY (le lot reste alors « prêt à ranger »).
    """
    from django.conf import settings

    return bool(
        getattr(settings, "DOSSIER_AUTO_APPLY", False)
        and not preview.get("question")
        and (preview.get("amm") or {}).get("id")
    )


def _auto_apply(batch, token: str) -> bool:
    """Rangement au nom de l'auteur ; en cas d'échec le lot reste « prêt à ranger » (READY)."""
    from .dossier.application import apply_dossier

    try:
        apply_dossier(batch.pk, user=batch.created_by, token=token, auto=True)
    except Exception:
        logger.exception("Rangement automatique du dossier %s impossible", batch.pk)
        return False
    logger.info("Dossier %s rangé automatiquement", batch.pk)
    return True
