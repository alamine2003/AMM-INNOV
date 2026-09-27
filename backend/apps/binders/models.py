"""Vérification des classeurs papier, page par page (une page = une AMM).

Les classeurs eux-mêmes ne sont pas stockés : ils se déduisent des AMM (pays, gamme, ordre
alphabétique des produits), voir `layout`. Seul ce que l'archiviste constate est enregistré.
"""

import uuid

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class BinderCheck(models.Model):
    """Ce que l'archiviste a constaté sur la page papier d'une AMM."""

    class Result(models.TextChoices):
        CONFORME = "CONFORME", "Conforme"
        CORRIGE = "CORRIGE", "Corrigé"
        ABSENT = "ABSENT", "Absent du classeur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    amm = models.OneToOneField(
        "amm.MarketingAuthorization",
        on_delete=models.CASCADE,
        related_name="binder_check",
        verbose_name="AMM",
    )
    result = models.CharField("constat", max_length=16, choices=Result.choices)
    # Champs corrigés par l'archiviste : [{"slot", "field", "old", "new"}].
    corrections = models.JSONField("corrections", default=list, blank=True)
    note = models.TextField("note", blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="vérifié par",
    )
    checked_at = models.DateTimeField("vérifié le")
    history = HistoricalRecords()

    class Meta:
        verbose_name = "vérification de classeur"
        verbose_name_plural = "vérifications de classeur"

    def __str__(self) -> str:
        return f"{self.amm} — {self.get_result_display()}"

    @property
    def physical_present(self) -> bool:
        return self.result != self.Result.ABSENT


class BinderExtraPage(models.Model):
    """Dossier trouvé dans un classeur papier sans AMM correspondante dans l'application."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    country = models.ForeignKey(
        "catalog.Country", on_delete=models.CASCADE, related_name="+", verbose_name="pays"
    )
    binder_key = models.CharField("classeur", max_length=40, db_index=True)
    product_name = models.CharField("produit lu sur le dossier", max_length=255)
    note = models.TextField("note", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="signalé par",
    )
    created_at = models.DateTimeField("signalé le", auto_now_add=True)

    class Meta:
        verbose_name = "page en trop"
        verbose_name_plural = "pages en trop"
        ordering = ["product_name"]

    def __str__(self) -> str:
        return f"{self.binder_key} — {self.product_name}"


def export_upload_to(instance, filename: str) -> str:
    return f"binders/{instance.binder_key}/{instance.pk}.pdf"


class BinderExport(models.Model):
    """Classeur complet avec les décisions officielles, assemblé en arrière-plan (siège)."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        RUNNING = "RUNNING", "En préparation"
        READY = "READY", "Prêt"
        FAILED = "FAILED", "Échec"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    country = models.ForeignKey(
        "catalog.Country", on_delete=models.CASCADE, related_name="+", verbose_name="pays"
    )
    binder_key = models.CharField("classeur", max_length=40, db_index=True)
    status = models.CharField(
        "statut", max_length=16, choices=Status.choices, default=Status.PENDING
    )
    progress_done = models.PositiveIntegerField("AMM traitées", default=0)
    progress_total = models.PositiveIntegerField("AMM à traiter", default=0)
    file = models.FileField("fichier", upload_to=export_upload_to, max_length=300, blank=True)
    size_bytes = models.PositiveBigIntegerField("taille (octets)", default=0)
    page_count = models.PositiveIntegerField("pages", default=0)
    decisions = models.PositiveIntegerField("décisions jointes", default=0)
    unavailable = models.PositiveIntegerField("scans illisibles ou absents du stockage", default=0)
    without_scan = models.PositiveIntegerField("AMM sans scan", default=0)
    error = models.TextField("erreur", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="demandé par",
    )
    created_at = models.DateTimeField("demandé le", auto_now_add=True)
    started_at = models.DateTimeField("commencé le", null=True, blank=True)
    finished_at = models.DateTimeField("terminé le", null=True, blank=True)

    ACTIVE = (Status.PENDING, Status.RUNNING)

    class Meta:
        verbose_name = "export de classeur"
        verbose_name_plural = "exports de classeur"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.binder_key} — {self.get_status_display()}"
