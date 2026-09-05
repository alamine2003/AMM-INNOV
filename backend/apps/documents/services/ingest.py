"""Upload pipeline: real MIME check (magic bytes), size limit, SHA-256, image -> PDF.

JPEG/PNG scans (phone photos) are converted losslessly to PDF with `img2pdf`, so that every
document is a PDF for the viewer, the ZIP archive and the page counter. A corrupted image is
refused (400) rather than stored as-is.
"""

import hashlib
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.dates import today as reference_today
from apps.core.tasks import enqueue
from apps.documents.models import Document

MAGIC_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", "application/pdf"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def detect_content_type(head: bytes) -> str | None:
    for signature, mime in MAGIC_SIGNATURES:
        if head.startswith(signature):
            return mime
    return None


def convert_image_to_pdf(content: bytes) -> bytes | None:
    """Lossless image -> PDF (img2pdf embeds the original bytes). None when the image is invalid."""
    import img2pdf  # type: ignore

    try:
        return img2pdf.convert(content)
    except Exception:
        return None


def default_document_date(amm, renewal=None) -> date:
    if renewal is not None and renewal.start_date:
        return renewal.start_date
    if amm.original_start_date:
        return amm.original_start_date
    return reference_today()


def read_upload(uploaded_file) -> bytes:
    max_bytes = settings.DOCUMENT_MAX_MB * 1024 * 1024
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > max_bytes:
        size_mb = size // (1024 * 1024)
        raise ValidationError(
            {"file": f"Fichier trop volumineux ({size_mb} Mo > {settings.DOCUMENT_MAX_MB} Mo)."}
        )
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    content = uploaded_file.read()
    if len(content) > max_bytes:
        raise ValidationError(
            {"file": f"Fichier trop volumineux (> {settings.DOCUMENT_MAX_MB} Mo)."}
        )
    if not content:
        raise ValidationError({"file": "Fichier vide."})
    return content


@transaction.atomic
def ingest_document(
    amm,
    uploaded_file,
    kind: str,
    *,
    document_date: date | None = None,
    title: str = "",
    renewal=None,
    user=None,
    replaces: Document | None = None,
) -> Document:
    """Validates and stores an upload. Raises ValidationError on refusal."""
    if kind not in Document.Kind.values:
        raise ValidationError({"kind": f"Type de document inconnu : {kind}."})
    content = read_upload(uploaded_file)
    content_type = detect_content_type(content[:16])
    if content_type is None:
        raise ValidationError(
            {"file": "Format non accepté : seuls PDF, JPEG et PNG sont acceptés."}
        )
    if content_type != "application/pdf":
        converted = convert_image_to_pdf(content)
        if converted is None:
            raise ValidationError({"file": "Image illisible : impossible de la convertir en PDF."})
        content, content_type = converted, "application/pdf"
    sha256 = hashlib.sha256(content).hexdigest()
    duplicate_error = ValidationError(
        {"file": "Ce fichier existe déjà pour cette AMM (empreinte SHA-256 identique)."}
    )
    if Document.objects.filter(amm=amm, sha256=sha256, archived_at__isnull=True).exists():
        raise duplicate_error
    if renewal is None and replaces is not None:
        renewal = replaces.renewal
    document = Document(
        amm=amm,
        renewal=renewal,
        kind=kind,
        title=title or "",
        document_date=document_date or default_document_date(amm, renewal),
        content_type=content_type,
        sha256=sha256,
        size_bytes=len(content),
        version=(replaces.version + 1) if replaces else 1,
        replaces=replaces,
        uploaded_by=user,
    )
    if user is not None:
        document._history_user = user
    extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[content_type]
    original_name = getattr(uploaded_file, "name", "") or "document"
    document.file.save(
        f"{original_name.rsplit('.', 1)[0]}.{extension}", ContentFile(content), save=False
    )
    try:
        with transaction.atomic():
            document.save()
    except IntegrityError:  # envoi simultané du même fichier : la contrainte tranche
        document.file.delete(save=False)
        raise duplicate_error
    if replaces is not None:
        replaces.is_current = False
        if user is not None:
            replaces._history_user = user
        replaces.save(update_fields=["is_current"])
    from apps.documents.tasks import generate_document_preview

    enqueue(generate_document_preview, str(document.pk))
    return document


def archive_document(document: Document, user=None) -> Document:
    document.archived_at = timezone.now()
    if user is not None:
        document._history_user = user
    document.save(update_fields=["archived_at"])
    return document
