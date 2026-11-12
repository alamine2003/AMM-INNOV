"""Modèles du socle : la corbeille, le journal des erreurs."""

import uuid

from django.conf import settings
from django.db import models


class TrashEntry(models.Model):
    """Un élément mis à la corbeille, avec tout ce qui partait avec lui.

    Rien n'est effacé de l'application : au lieu d'être supprimés, l'élément et les lignes qui
    l'accompagnaient (renouvellements, pièces, alertes…) sont copiés ici, puis retirés de leurs
    tables. Un administrateur peut les restaurer tels quels. La corbeille n'est jamais vidée :
    une entrée restaurée reste, marquée restaurée (qui, quand).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    label = models.CharField("élément", max_length=300)
    kind = models.CharField("type", max_length=100)  # « page du classeur », « renouvellement »…
    model = models.CharField("modèle", max_length=100)  # app_label.model de l'élément
    object_id = models.CharField("identifiant", max_length=64)
    country = models.CharField("pays", max_length=2, blank=True)
    reason = models.CharField("motif", max_length=300, blank=True)
    # {"objects": [sérialisation Django], "updates": [[modèle, pk, champ, ancienne valeur]]}
    payload = models.JSONField("contenu")
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="supprimé par",
    )
    deleted_at = models.DateTimeField("supprimé le", auto_now_add=True, db_index=True)
    restored_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="restauré par",
    )
    restored_at = models.DateTimeField("restauré le", null=True, blank=True)

    class Meta:
        verbose_name = "élément de la corbeille"
        verbose_name_plural = "corbeille"
        ordering = ["-deleted_at"]

    def __str__(self) -> str:
        return f"{self.kind} : {self.label}"


class ErrorEvent(models.Model):
    """Une erreur survenue en production (serveur, worker ou interface), regroupée par empreinte.

    Remplace Sentry sans compte externe (audit du 11/11/2026, constat 11) : rien ne sort
    d'AMM GH. La même erreur qui se répète incrémente `count` au lieu d'ajouter des lignes.
    """

    class Source(models.TextChoices):
        SERVER = "server", "Serveur"
        WORKER = "worker", "Tâche de fond"
        INTERFACE = "interface", "Interface"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fingerprint = models.CharField("empreinte", max_length=64, unique=True)
    source = models.CharField("origine", max_length=16, choices=Source.choices)
    kind = models.CharField("type", max_length=120)  # ValueError, TypeError…
    message = models.CharField("message", max_length=500)
    detail = models.TextField("détail", blank=True)  # pile d'appels, tronquée
    location = models.CharField("où", max_length=300, blank=True)  # chemin ou tâche
    version = models.CharField("version", max_length=20, blank=True)
    count = models.PositiveIntegerField("occurrences", default=1)
    first_seen = models.DateTimeField("première fois", auto_now_add=True)
    last_seen = models.DateTimeField("dernière fois", db_index=True)
    last_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="dernier utilisateur",
    )
    resolved_at = models.DateTimeField("résolue le", null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="résolue par",
    )

    class Meta:
        verbose_name = "erreur"
        verbose_name_plural = "journal des erreurs"
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"{self.kind} : {self.message[:80]}"
