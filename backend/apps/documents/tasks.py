"""Document background jobs: page counting (pypdf) and yearly purge of old archives."""

import logging

from celery import shared_task
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone

from .models import Document

logger = logging.getLogger(__name__)


@shared_task(name="apps.documents.tasks.generate_document_preview")
def generate_document_preview(document_id: str) -> dict:
    """Computes `page_count` for PDF documents (thumbnails are out of scope for the MVP)."""
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return {"status": "missing"}
    if document.content_type != "application/pdf":
        return {"status": "skipped"}
    try:
        from pypdf import PdfReader

        document.file.open("rb")
        try:
            count = len(PdfReader(document.file).pages)
        finally:
            document.file.close()
    except Exception as exc:  # pragma: no cover - corrupted PDF
        logger.warning("Impossible de compter les pages de %s : %s", document_id, exc)
        return {"status": "error"}
    Document.objects.filter(pk=document.pk).update(page_count=count)
    return {"status": "ok", "page_count": count}


@shared_task(name="apps.documents.tasks.purge_archived_documents")
def purge_archived_documents() -> dict:
    """Physically deletes documents archived for more than DOCUMENT_RETENTION_YEARS."""
    limit = timezone.now() - relativedelta(years=settings.DOCUMENT_RETENTION_YEARS)
    purged = 0
    for document in Document.objects.filter(archived_at__lt=limit):
        document.file.delete(save=False)
        document.delete()
        purged += 1
    return {"purged": purged}
