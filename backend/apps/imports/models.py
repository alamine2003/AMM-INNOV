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
        # Lu, AMM identifiée, pas encore rangé (rangement automatique désactivé ou en échec).
        READY = "READY", "Prêt à ranger"
        # L'AMM cible n'est pas identifiable : une seule question, « c'est quelle AMM ? ».
        QUESTION = "QUESTION", "Question : quelle AMM ?"
        APPLIED = "APPLIED", "Rangé"
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
    # Bilan de ce que la validation a réellement changé (état avant/après de l'AMM,
    # renouvellements créés, documents rattachés, champs modifiés). Rempli après commit.
    summary = models.JSONField(default=dict, blank=True)
    # Rangé sans intervention humaine dès l'AMM identifiée (voir `apps.imports.tasks`) ; aucune
    # valeur enregistrée n'est remplacée. L'auteur de l'import reste le validateur tracé.
    auto_applied = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # Début de l'analyse en cours : au-delà de sa durée maximale, une analyse RUNNING est
    # orpheline (worker tué, s12b) et recover_pending_work la rend relançable.
    started_at = models.DateTimeField(null=True, blank=True)
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


class DossierReviewPoint(models.Model):
    """« Point à vérifier plus tard » : écart ou doute relevé par un import, jamais bloquant.

    L'import garde la valeur de la fiche et range quand même le scan. Le réglementaire décide
    plus tard, depuis la fiche AMM ou le lot : « Appliquer la valeur du scan » (tracé comme une
    `DossierChange`) ou « Ignorer ».
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "À vérifier"
        APPLIED = "APPLIED", "Valeur du scan appliquée"
        IGNORED = "IGNORED", "Ignoré"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch = models.ForeignKey(DossierImport, on_delete=models.CASCADE, related_name="review_points")
    amm = models.ForeignKey(
        "amm.MarketingAuthorization", on_delete=models.CASCADE, related_name="review_points"
    )
    renewal = models.ForeignKey(
        "amm.Renewal", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    code = models.CharField(max_length=32)
    # Champ concerné (vide pour un simple doute sans valeur à appliquer).
    field = models.CharField(max_length=100, blank=True)
    recorded_value = models.JSONField(null=True, blank=True)
    scan_value = models.JSONField(null=True, blank=True)
    proof_file = models.ForeignKey(
        DossierFile, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    confidence = models.PositiveSmallIntegerField(default=0)
    message = models.TextField()
    # Empreinte de l'écart : un même dossier réimporté ne recrée pas le point.
    fingerprint = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["amm", "status"], name="review_point_amm_status")]

    def __str__(self):
        return self.message[:80]

    @property
    def applicable(self) -> bool:
        return bool(self.field) and self.scan_value not in (None, "")
