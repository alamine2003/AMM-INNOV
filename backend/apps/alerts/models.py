"""Alert rules (global or per country) and the alerts they produce."""

import uuid

from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords


class AlertRule(models.Model):
    class Severity(models.TextChoices):
        INFO = "INFO", "Information"
        WARNING = "WARNING", "Avertissement"
        CRITICAL = "CRITICAL", "Critique"

    class Channel(models.TextChoices):
        IN_APP = "IN_APP", "In-app"
        EMAIL = "EMAIL", "Email"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField("code", max_length=32)
    country = models.ForeignKey(
        "catalog.Country",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="alert_rules",
        verbose_name="pays (vide = globale)",
    )
    offset_days = models.IntegerField("délai avant échéance (jours)", default=180)
    severity = models.CharField(
        "sévérité", max_length=16, choices=Severity.choices, default=Severity.WARNING
    )
    roles = models.JSONField("rôles destinataires", default=list)
    channels = models.JSONField("canaux", default=list)
    only_if_not_filed = models.BooleanField("seulement si aucun dépôt", default=True)
    is_active = models.BooleanField("active", default=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "règle d'alerte"
        verbose_name_plural = "règles d'alerte"
        unique_together = [("code", "country")]
        ordering = ["-offset_days", "code"]

    def __str__(self) -> str:
        scope = self.country.iso2 if self.country_id else "global"
        return f"{self.code} ({scope})"


class Alert(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Ouverte"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acquittée"
        RESOLVED = "RESOLVED", "Résolue"

    class Resolution(models.TextChoices):
        AUTO_FILED = "AUTO_FILED", "Dépôt enregistré"
        AUTO_RENEWED = "AUTO_RENEWED", "Renouvellement obtenu"
        MANUAL = "MANUAL", "Résolution manuelle"

    OPEN_STATUSES = (Status.OPEN, Status.ACKNOWLEDGED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    amm = models.ForeignKey(
        "amm.MarketingAuthorization", on_delete=models.CASCADE, related_name="alerts"
    )
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name="alerts")
    due_date = models.DateField("échéance")
    status = models.CharField(
        "statut", max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_alerts",
        verbose_name="assignée à",
    )
    triggered_at = models.DateTimeField("déclenchée le", auto_now_add=True)
    acknowledged_at = models.DateTimeField("acquittée le", null=True, blank=True)
    resolved_at = models.DateTimeField("résolue le", null=True, blank=True)
    resolution = models.CharField(
        "résolution", max_length=16, choices=Resolution.choices, null=True, blank=True
    )
    comment = models.TextField("commentaire", blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = "alerte"
        verbose_name_plural = "alertes"
        unique_together = [("amm", "rule", "due_date")]
        ordering = ["due_date", "-triggered_at"]

    def __str__(self) -> str:
        return f"{self.rule.code} — {self.amm} — {self.due_date:%d/%m/%Y}"
