from datetime import date

from celery import shared_task

from .models import ImportBatch
from .services import import_workbook


@shared_task(name="apps.imports.tasks.run_import")
def run_import(batch_id: str, today: str | None = None) -> dict:
    batch = ImportBatch.objects.get(pk=batch_id)
    reference = date.fromisoformat(today) if today else batch.reference_date
    batch.file.open("rb")
    try:
        summary = import_workbook(batch.file, batch=batch, today=reference)
    finally:
        batch.file.close()
    return summary.get("totals", {})
