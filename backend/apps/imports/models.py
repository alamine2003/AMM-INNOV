import uuid

from django.conf import settings
from django.db import models


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        RUNNING = "RUNNING", "En cours"
        DONE = "DONE", "Terminé"
        FAILED = "FAILED", "Échoué"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField("classeur", upload_to="imports/%Y/%m/", max_length=500)
    status = models.CharField(
        "statut", max_length=16, choices=Status.choices, default=Status.PENDING
    )
    summary = models.JSONField("résumé", default=dict, blank=True)
    reference_date = models.DateField("date de référence", null=True, blank=True)
    # Simulation : le rapport (lignes, compteurs, anomalies) est produit, rien n'est écrit.
    dry_run = models.BooleanField("simulation", default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="imports",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "import"
        verbose_name_plural = "imports"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Import {self.created_at:%d/%m/%Y %H:%M} — {self.get_status_display()}"


class ImportRow(models.Model):
    class Outcome(models.TextChoices):
        CREATED = "CREATED", "Créée"
        UPDATED = "UPDATED", "Mise à jour"
        SKIPPED = "SKIPPED", "Inchangée"
        ERROR = "ERROR", "Erreur"
        WARNING = "WARNING", "Avertissement"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    sheet = models.CharField("onglet", max_length=100)
    row_number = models.PositiveIntegerField("ligne")
    raw = models.JSONField("données brutes", default=dict)
    outcome = models.CharField("résultat", max_length=16, choices=Outcome.choices)
    message = models.TextField("message", blank=True)
    amm = models.ForeignKey(
        "amm.MarketingAuthorization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "ligne d'import"
        verbose_name_plural = "lignes d'import"
        ordering = ["sheet", "row_number"]

    def __str__(self) -> str:
        return f"{self.sheet}!{self.row_number} — {self.outcome}"


def dossier_upload_to(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower()
    return f"imports/dossiers/{instance.batch_id}/{uuid.uuid4().hex}.{extension}"


class DossierImport(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        RUNNING = "RUNNING", "Analyse en cours"
        READY = "READY", "À valider"
        APPLIED = "APPLIED", "Enregistré"
        FAILED = "FAILED", "Analyse échouée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    root_name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dossier_imports",
    )
    country = models.ForeignKey("catalog.Country", on_delete=models.PROTECT, null=True, blank=True)
    amm = models.ForeignKey(
        "amm.MarketingAuthorization",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dossier_imports",
    )
    preview = models.JSONField(default=dict, blank=True)
    preview_token = models.CharField(max_length=64, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.root_name


class DossierFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(DossierImport, on_delete=models.CASCADE, related_name="files")
    relative_path = models.CharField(max_length=500)
    file = models.FileField(upload_to=dossier_upload_to, max_length=500)
    sha256 = models.CharField(max_length=64, db_index=True)
    content_type = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    extraction = models.JSONField(default=dict, blank=True)
    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dossier_sources",
    )

    class Meta:
        ordering = ["relative_path"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "relative_path"], name="dossier_path_unique"),
        ]

    def __str__(self):
        return self.relative_path


class DossierChange(models.Model):
    """Append-only documentary provenance, in addition to django-simple-history."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(DossierImport, on_delete=models.PROTECT, related_name="audit")
    amm = models.ForeignKey(
        "amm.MarketingAuthorization", on_delete=models.PROTECT, related_name="documentary_changes"
    )
    renewal = models.ForeignKey("amm.Renewal", on_delete=models.PROTECT, null=True, blank=True)
    field = models.CharField(max_length=100)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    proof_file = models.ForeignKey(DossierFile, on_delete=models.PROTECT, related_name="changes")
    confidence = models.PositiveSmallIntegerField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=32, default="DOSSIER_IMPORT", editable=False)
    reason = models.CharField(
        max_length=255, default="Correction à partir du dossier réglementaire importé"
    )

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=100),
                name="dossier_change_confidence_range",
            ),
        ]

    def __str__(self):
        return f"{self.amm_id} / {self.field}"
