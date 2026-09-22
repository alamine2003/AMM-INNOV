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
        preview = build_preview(batch)
        # Un pays reconnu hors du périmètre de l'auteur n'est pas enregistré sur le lot :
        # sinon le lot disparaît de sa liste (404) et il ne voit jamais le blocage expliqué.
        country_id = preview.get("amm", {}).get("country_id")
        if country_id and not batch.created_by.can_access_country(country_id):
            country_id = batch.country_id
        DossierImport.objects.filter(pk=batch_id, status=DossierImport.Status.RUNNING).update(
            status=DossierImport.Status.READY,
            preview=preview,
            preview_token=preview_token(preview),
            country_id=country_id,
            finished_at=timezone.now(),
        )
        return {"status": "ready", "confidence": preview["confidence"]}
    except Exception:
        logger.exception("Échec de l'analyse du dossier %s", batch_id)
        DossierImport.objects.filter(pk=batch_id, status=DossierImport.Status.RUNNING).update(
            status=DossierImport.Status.FAILED,
            finished_at=timezone.now(),
            error="L'analyse a échoué. Vérifiez les documents puis relancez l'analyse.",
        )
        return {"status": "failed"}
