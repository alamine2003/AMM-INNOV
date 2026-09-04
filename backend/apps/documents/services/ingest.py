"""Upload pipeline: real MIME check (magic bytes), size limit, SHA-256, optional image -> PDF.

Images are converted with `img2pdf` when the package is installed; otherwise the JPEG/PNG
is stored as-is with its real content type (documented in the README).
"""

import hashlib
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
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
    try:
        import img2pdf  # type: ignore
    except ImportError:
        return None
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
        if converted:
            content, content_type = converted, "application/pdf"
    sha256 = hashlib.sha256(content).hexdigest()
    duplicate = Document.objects.filter(amm=amm, sha256=sha256, archived_at__isnull=True)
    if replaces is not None:
        duplicate = duplicate.exclude(pk=replaces.pk)
    if duplicate.exists():
        raise ValidationError(
            {"file": "Ce fichier existe déjà pour cette AMM (empreinte SHA-256 identique)."}
        )
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
    document.save()
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
