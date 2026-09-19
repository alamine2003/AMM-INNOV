"""Document background jobs: page counting (pypdf) and yearly purge of old archives."""

import logging

from celery import shared_task
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
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
    from pypdf import PdfReader

    # Prise en charge avant l'analyse : page_count 0 = « tenté ». Si le PDF tue le processus
    # (mémoire), la tâche redistribuée (acks tardifs) et le rattrapage le trouvent déjà tenté
    # au lieu de le relancer en boucle.
    if not Document.objects.filter(pk=document.pk, page_count__isnull=True).update(page_count=0):
        return {"status": "already-done"}
    try:
        document.file.open("rb")
        document.file.read(0)  # S3 : téléchargement ici
    except Exception as exc:
        # stockage indisponible : on rend la main, recover_pending_work réessaiera
        Document.objects.filter(pk=document.pk).update(page_count=None)
        logger.warning("Scan %s illisible pour l'instant (stockage) : %s", document_id, exc)
        return {"status": "storage-unavailable"}
    try:
        count = len(PdfReader(document.file).pages)
    except Exception as exc:
        # PDF illisible : 0 (« inconnu », non affiché) pour que le rattrapage ne le reprenne pas
        # toutes les 5 minutes (campagne de chaos : 410 tâches par passage sur des PDF invalides)
        logger.warning("Impossible de compter les pages de %s : %s", document_id, exc)
        count = 0
    finally:
        document.file.close()
    Document.objects.filter(pk=document.pk).update(page_count=count)
    return {"status": "ok" if count else "unreadable", "page_count": count}


@shared_task(name="apps.documents.tasks.purge_archived_documents")
def purge_archived_documents() -> dict:
    """Physically deletes documents archived for more than DOCUMENT_RETENTION_YEARS."""
    limit = timezone.now() - relativedelta(years=settings.DOCUMENT_RETENTION_YEARS)
    purged = 0
    for document in Document.objects.filter(archived_at__lt=limit):
        storage, name = document.file.storage, document.file.name
        with transaction.atomic():
            # Les fichiers d'un dossier importé conservent leur propre blob : on détache la
            # référence (PROTECT) avant de supprimer le document.
            document.dossier_sources.update(document=None)
            document.delete()
            # Le fichier part après la ligne : un crash entre les deux laisse au pire un fichier
            # orphelin, jamais une ligne pointant vers un fichier disparu (H15).
            transaction.on_commit(lambda storage=storage, name=name: _delete_blob(storage, name))
        purged += 1
    return {"purged": purged}


def _delete_blob(storage, name: str) -> None:
    try:
        storage.delete(name)
    except Exception:
        logger.warning("Fichier %s non supprimé : orphelin à nettoyer", name)
