"""Dépôt des AMM : le dossier de renouvellement, du montage au siège jusqu'à la décision.

Procédure (rubrique « Dépôt AMM ») :

1. le siège monte le dossier selon la liste des pièces du pays (lettre de demande, certificat
   de PGHT, formulaires, RCP, certificats d'analyse, pièces réglementaires) ;
2. il récupère les échantillons sur place et note n° de lot, date de fabrication et date de
   péremption ;
3. il envoie le dossier au pays : le pays est prévenu et télécharge le dossier complet ;
4. le pays dépose le dossier à l'agence et renvoie l'attestation de dépôt au siège ;
5. le dépôt passe en commission ; notifications et commissions sont notées au fil de l'eau ;
6. la décision clôt le dossier (renouvellement obtenu ou rejeté).

L'étape se déduit des données (et du renouvellement lié), elle n'est jamais saisie : un
renouvellement conclu ailleurs (fiche AMM, import de dossier) clôt aussi le dépôt.
"""

import uuid

from django.conf import settings
from django.db import models


def piece_upload_to(instance, filename: str) -> str:
    amm = instance.dossier.renewal.amm
    folder = f"depots/{amm.country.iso2}/{amm.pk}/{instance.dossier_id}"
    return f"{folder}/{uuid.uuid4().hex[:8]}_{filename}"


def event_upload_to(instance, filename: str) -> str:
    amm = instance.dossier.renewal.amm
    return (
        f"depots/{amm.country.iso2}/{amm.pk}/{instance.dossier_id}/suivi/"
        f"{uuid.uuid4().hex[:8]}_{filename}"
    )


class PieceType(models.Model):
    """Pièce du dossier. Sans pays : liste de base, commune à tous les pays ; avec un pays :
    pièce propre à ce pays. Une pièce de base peut être retirée pour certains pays."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField("pièce", max_length=200)
    help_text = models.CharField("précision", max_length=500, blank=True)
    required = models.BooleanField("obligatoire", default=True)
    order = models.PositiveSmallIntegerField("ordre", default=100)
    country = models.ForeignKey(
        "catalog.Country",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="deposit_pieces",
        verbose_name="pays (pièce propre au pays)",
    )
    excluded_countries = models.ManyToManyField(
        "catalog.Country",
        blank=True,
        related_name="deposit_pieces_excluded",
        verbose_name="pays qui ne la demandent pas",
    )
    active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "pièce du dossier de dépôt"
        verbose_name_plural = "pièces du dossier de dépôt"
        ordering = ["order", "label"]

    def __str__(self) -> str:
        return self.label


class DepositDossier(models.Model):
    class Stage(models.TextChoices):
        MONTAGE = "MONTAGE", "Montage du dossier"
        ENVOYE = "ENVOYE", "Envoyé au pays"
        DEPOSE = "DEPOSE", "Déposé à l'agence"
        COMMISSION = "COMMISSION", "En commission"
        OBTENU = "OBTENU", "Renouvellement obtenu"
        REJETE = "REJETE", "Rejeté"
        ABANDONNE = "ABANDONNE", "Abandonné"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    renewal = models.OneToOneField(
        "amm.Renewal",
        on_delete=models.CASCADE,
        related_name="deposit",
        verbose_name="renouvellement",
    )
    samples_required = models.BooleanField("échantillons demandés", default=True)
    sent_at = models.DateTimeField("envoyé au pays le", null=True, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    send_note = models.TextField("message d'envoi", blank=True)
    deposited_at = models.DateTimeField("attestation reçue le", null=True, blank=True)
    deposited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    attestation = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="attestation de dépôt",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "dossier de dépôt"
        verbose_name_plural = "dossiers de dépôt"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Dépôt {self.renewal}"

    @property
    def stage(self) -> str:
        from apps.amm.models import Renewal

        status = self.renewal.workflow_status
        if status in (Renewal.WorkflowStatus.OBTENU, Renewal.WorkflowStatus.REJETE):
            return status
        if status == Renewal.WorkflowStatus.ABANDONNE:
            return self.Stage.ABANDONNE
        if status == Renewal.WorkflowStatus.EN_INSTRUCTION:
            return self.Stage.COMMISSION
        if status == Renewal.WorkflowStatus.DEPOSE or self.deposited_at:
            return self.Stage.DEPOSE
        if self.sent_at:
            return self.Stage.ENVOYE
        return self.Stage.MONTAGE


class DepositPiece(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(DepositDossier, on_delete=models.CASCADE, related_name="pieces")
    piece_type = models.ForeignKey(
        PieceType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="pièce (vide : autre pièce)",
    )
    label = models.CharField("libellé", max_length=200, blank=True)
    file = models.FileField("fichier", upload_to=piece_upload_to, max_length=500)
    filename = models.CharField("nom du fichier", max_length=255)
    content_type = models.CharField("type MIME", max_length=128, blank=True)
    size_bytes = models.PositiveBigIntegerField("taille", default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pièce jointe au dossier"
        ordering = ["uploaded_at"]

    def __str__(self) -> str:
        return f"{self.label} : {self.filename}"


class DepositSample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(DepositDossier, on_delete=models.CASCADE, related_name="samples")
    batch_number = models.CharField("n° de lot", max_length=100)
    manufactured_on = models.DateField("date de fabrication")
    expires_on = models.DateField("date de péremption")
    quantity = models.PositiveIntegerField("quantité", null=True, blank=True)
    note = models.CharField("remarque", max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "échantillon"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Lot {self.batch_number}"


class DepositEvent(models.Model):
    """Suivi à l'agence : passages en commission, notifications, demandes de complément."""

    class Kind(models.TextChoices):
        COMMISSION = "COMMISSION", "Passage en commission"
        NOTIFICATION = "NOTIFICATION", "Notification de l'agence"
        COMPLEMENT = "COMPLEMENT", "Demande de complément"
        AUTRE = "AUTRE", "Autre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(DepositDossier, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField("type", max_length=16, choices=Kind.choices)
    date = models.DateField("date")
    note = models.TextField("détail", blank=True)
    file = models.FileField("pièce", upload_to=event_upload_to, max_length=500, blank=True)
    filename = models.CharField("nom du fichier", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "suivi à l'agence"
        ordering = ["date", "created_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} du {self.date:%d/%m/%Y}"


class DepositMessage(models.Model):
    """Échanges entre le siège et le pays sur un dossier."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(DepositDossier, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    body = models.TextField("message")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "message"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return self.body[:60]


class DepositActivity(models.Model):
    """Journal du dossier : qui a fait quoi, quand (téléchargements compris)."""

    class Kind(models.TextChoices):
        CREE = "CREE", "Dossier ouvert"
        PIECE = "PIECE", "Pièce ajoutée"
        PIECE_RETIREE = "PIECE_RETIREE", "Pièce retirée"
        ECHANTILLON = "ECHANTILLON", "Échantillon noté"
        ENVOI = "ENVOI", "Envoyé au pays"
        TELECHARGEMENT = "TELECHARGEMENT", "Dossier téléchargé"
        DEPOT = "DEPOT", "Déposé à l'agence"
        SUIVI = "SUIVI", "Suivi à l'agence"
        DECISION = "DECISION", "Décision"
        ABANDON = "ABANDON", "Abandon"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(DepositDossier, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField("type", max_length=16, choices=Kind.choices)
    text = models.CharField("détail", max_length=500)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "activité"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.text
