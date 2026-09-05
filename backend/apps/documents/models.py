"""Scanned documents (AMM, receipts, letters) with versioning and logical deletion."""

import uuid

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


def document_upload_to(instance, filename: str) -> str:
    """`documents/{iso2}/{product_slug}/{amm_id}/{date}_{kind}_v{version}_{uuid8}.{ext}`."""
    ext = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf") or "pdf"
    amm = instance.amm
    date_prefix = (
        instance.document_date.strftime("%Y-%m-%d") if instance.document_date else "0000-00-00"
    )
    return (
        f"documents/{amm.country.iso2}/{amm.product.slug}/{amm.pk}/"
        f"{date_prefix}_{instance.kind}_v{instance.version}_{uuid.uuid4().hex[:8]}.{ext}"
    )


class DocumentQuerySet(models.QuerySet):
    def current(self):
        return self.filter(is_current=True, archived_at__isnull=True)


class DocumentManager(models.Manager.from_queryset(DocumentQuerySet)):
    """Canonical order everywhere: most recent first (`-document_date, -uploaded_at`)."""

    def get_queryset(self):
        return super().get_queryset().order_by("-document_date", "-uploaded_at")

    def current(self):
        return self.get_queryset().current()


class Document(models.Model):
    class Kind(models.TextChoices):
        AMM = "AMM", "AMM"
        RECEPISSE = "RECEPISSE", "Récépissé de dépôt"
        COURRIER = "COURRIER", "Courrier de l'autorité"
        AUTRE = "AUTRE", "Autre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    amm = models.ForeignKey(
        "amm.MarketingAuthorization",
        on_delete=models.CASCADE,
        related_name="documents",
        verbose_name="AMM",
    )
    renewal = models.ForeignKey(
        "amm.Renewal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
        verbose_name="renouvellement",
    )
    kind = models.CharField("type", max_length=16, choices=Kind.choices, default=Kind.AMM)
    title = models.CharField("titre", max_length=255, blank=True)
    document_date = models.DateField("date du document", db_index=True)
    file = models.FileField("fichier", upload_to=document_upload_to, max_length=500)
    content_type = models.CharField("type MIME", max_length=64, default="application/pdf")
    sha256 = models.CharField("empreinte SHA-256", max_length=64, db_index=True)
    size_bytes = models.PositiveBigIntegerField("taille (octets)", default=0)
    page_count = models.PositiveIntegerField("nombre de pages", null=True, blank=True)
    version = models.PositiveIntegerField("version", default=1)
    replaces = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replaced_by",
        verbose_name="remplace",
    )
    is_current = models.BooleanField("version courante", default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
        verbose_name="téléversé par",
    )
    uploaded_at = models.DateTimeField("téléversé le", auto_now_add=True, db_index=True)
    archived_at = models.DateTimeField("archivé le", null=True, blank=True)
    history = HistoricalRecords()

    objects = DocumentManager()

    class Meta:
        verbose_name = "document"
        verbose_name_plural = "documents"
        ordering = ["-document_date", "-uploaded_at"]
        indexes = [
            models.Index(
                fields=["amm", "-document_date", "-uploaded_at"], name="doc_amm_chrono_idx"
            ),
        ]
        constraints = [
            # Le même fichier ne peut exister qu'une fois par AMM tant qu'il n'est pas archivé :
            # garantit l'anti-doublon même sous envois simultanés.
            models.UniqueConstraint(
                fields=["amm", "sha256"],
                condition=models.Q(archived_at__isnull=True),
                name="doc_amm_sha256_active_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.document_date:%d/%m/%Y} v{self.version}"

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def extension(self) -> str:
        return {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}.get(
            self.content_type, "bin"
        )

    def export_filename(self) -> str:
        """`{ISO2}_{PRODUIT}_{KIND}_{AAAA-MM-JJ}.pdf` (product label sanitized)."""
        import re

        product = re.sub(r"[^A-Z0-9]+", "_", self.amm.product.name.upper()).strip("_")[:60]
        return (
            f"{self.amm.country.iso2}_{product}_{self.kind}_"
            f"{self.document_date:%Y-%m-%d}.{self.extension}"
        )
