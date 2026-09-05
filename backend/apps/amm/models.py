"""Marketing authorizations (one per product x country) and their renewal history."""

import uuid

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class MarketingAuthorization(models.Model):
    class Status(models.TextChoices):
        VALIDE = "VALIDE", "Valide"
        EXPIRE = "EXPIRE", "Expirée"
        IN_PROCESS = "IN_PROCESS", "En cours d'instruction"
        INDETERMINE = "INDETERMINE", "Indéterminé"

    class Urgency(models.TextChoices):
        OK = "OK", "OK"
        A_PLANIFIER = "A_PLANIFIER", "À planifier"
        DEPOT_URGENT = "DEPOT_URGENT", "Dépôt urgent"
        CRITIQUE = "CRITIQUE", "Critique"
        EXPIRE = "EXPIRE", "Expirée"
        EN_INSTRUCTION = "EN_INSTRUCTION", "En instruction"

    class DossierState(models.TextChoices):
        COMPLET = "COMPLET", "Dossier complet"
        INCOMPLET = "INCOMPLET", "Dossier incomplet"
        INCONNU = "INCONNU", "Inconnu"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="amms", verbose_name="produit"
    )
    country = models.ForeignKey(
        "catalog.Country", on_delete=models.PROTECT, related_name="amms", verbose_name="pays"
    )
    original_number = models.CharField("n° AMM d'origine", max_length=100, blank=True)
    original_start_date = models.DateField("date de début d'origine", null=True, blank=True)
    original_end_date = models.DateField("date de fin d'origine", null=True, blank=True)
    original_end_date_manual = models.BooleanField("date de fin saisie manuellement", default=False)
    status = models.CharField(
        "statut", max_length=16, choices=Status.choices, default=Status.INDETERMINE, db_index=True
    )
    urgency = models.CharField(
        "urgence",
        max_length=16,
        choices=Urgency.choices,
        default=Urgency.A_PLANIFIER,
        db_index=True,
    )
    effective_end_date = models.DateField(
        "date de fin effective", null=True, blank=True, db_index=True
    )
    filing_deadline = models.DateField("deadline de dépôt", null=True, blank=True)
    dossier_state = models.CharField(
        "état du dossier", max_length=16, choices=DossierState.choices, default=DossierState.INCONNU
    )
    notes = models.TextField("notes", blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_amms",
        verbose_name="responsable",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    COMPUTED_FIELDS = ("status", "urgency", "effective_end_date", "filing_deadline")

    class Meta:
        verbose_name = "AMM"
        verbose_name_plural = "AMM"
        unique_together = [("product", "country")]
        ordering = ["country__iso2", "product__name"]
        indexes = [
            models.Index(fields=["country", "status"], name="amm_country_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product} / {self.country_id and self.country.iso2}"

    def save(self, *args, **kwargs):
        from .services.status import compute_amm_state

        if self.original_start_date and not self.original_end_date_manual:
            self.original_end_date = self.original_start_date + relativedelta(
                years=self.country.validity_years
            )
        elif not self.original_start_date and not self.original_end_date_manual:
            self.original_end_date = None
        state = compute_amm_state(self)
        state.apply_to(self)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            kwargs["update_fields"] = sorted(
                set(update_fields) | set(self.COMPUTED_FIELDS) | {"original_end_date"}
            )
        super().save(*args, **kwargs)


class Renewal(models.Model):
    class WorkflowStatus(models.TextChoices):
        PLANIFIE = "PLANIFIE", "Planifié"
        EN_PREPARATION = "EN_PREPARATION", "En préparation"
        DEPOSE = "DEPOSE", "Déposé"
        EN_INSTRUCTION = "EN_INSTRUCTION", "En instruction"
        OBTENU = "OBTENU", "Obtenu"
        REJETE = "REJETE", "Rejeté"
        ABANDONNE = "ABANDONNE", "Abandonné"

    PENDING_STATUSES = (WorkflowStatus.DEPOSE, WorkflowStatus.EN_INSTRUCTION)
    OPEN_STATUSES = (
        WorkflowStatus.PLANIFIE,
        WorkflowStatus.EN_PREPARATION,
        WorkflowStatus.DEPOSE,
        WorkflowStatus.EN_INSTRUCTION,
    )
    TERMINAL_STATUSES = (
        WorkflowStatus.OBTENU,
        WorkflowStatus.REJETE,
        WorkflowStatus.ABANDONNE,
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    amm = models.ForeignKey(
        MarketingAuthorization,
        on_delete=models.CASCADE,
        related_name="renewals",
        verbose_name="AMM",
    )
    sequence = models.PositiveIntegerField("n° d'ordre", editable=False)
    workflow_status = models.CharField(
        "statut du workflow",
        max_length=16,
        choices=WorkflowStatus.choices,
        default=WorkflowStatus.PLANIFIE,
    )
    filing_date = models.DateField("date de dépôt", null=True, blank=True)
    decision_date = models.DateField("date de décision", null=True, blank=True)
    number = models.CharField("n° AMM", max_length=100, blank=True)
    start_date = models.DateField("date de début", null=True, blank=True)
    end_date = models.DateField("date de fin", null=True, blank=True)
    end_date_manual = models.BooleanField("date de fin saisie manuellement", default=False)
    notes = models.TextField("notes", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "renouvellement"
        verbose_name_plural = "renouvellements"
        unique_together = [("amm", "sequence")]
        ordering = ["amm", "sequence"]

    def __str__(self) -> str:
        return f"Renouvellement {self.sequence} — {self.get_workflow_status_display()}"

    def save(self, *args, **kwargs):
        if self.sequence is None:
            last = (
                Renewal.objects.filter(amm=self.amm)
                .aggregate(models.Max("sequence"))
                .get("sequence__max")
            )
            self.sequence = (last or 0) + 1
        if self.start_date and not self.end_date_manual:
            self.end_date = self.start_date + relativedelta(years=self.amm.country.validity_years)
        elif not self.start_date and not self.end_date_manual:
            self.end_date = None
        super().save(*args, **kwargs)

    @property
    def is_pending(self) -> bool:
        return self.workflow_status in self.PENDING_STATUSES
