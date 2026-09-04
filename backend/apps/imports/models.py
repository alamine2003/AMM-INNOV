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
