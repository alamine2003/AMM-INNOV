"""Corbeille : supprimer sans rien perdre, restaurer à l'identique.

`move_to_trash(obj, user=…)` remplace `obj.delete()` partout où une personne supprime quelque
chose. Django rassemble ce que la suppression emporterait (lignes en cascade) et ce qu'elle
modifierait (liens mis à vide) : tout est copié dans une `TrashEntry`, puis supprimé comme avant.
`restore(entry, user=…)` remet les lignes avec les mêmes identifiants et rétablit les liens.

Les fichiers (scans, pièces) ne sont jamais effacés du stockage : la ligne restaurée retrouve
son fichier. Le socle ne connaît aucun modèle métier : les apps réagissent à une restauration
(recalcul de l'AMM, page à nouveau suivie…) par le registre `TRASH_RESTORED`.
"""

from __future__ import annotations

import json

from django.apps import apps
from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import IntegrityError, router, transaction
from django.db.models import FileField, ProtectedError
from django.db.models.deletion import Collector
from django.utils import timezone

from .models import TrashEntry
from .registry import Registry

# `f(obj)` : appelé sur chaque objet juste avant qu'il soit remis en place (par exemple un
# n° d'ordre déjà repris par un autre renouvellement entre-temps).
TRASH_PREPARE = Registry("préparation d'une restauration")

# `f(entry, objects, user)` : appelé après une restauration, avec les objets remis en place.
TRASH_RESTORED = Registry("restauration depuis la corbeille")

# Garde-fou : nombre de groupes de lignes traités pour une seule suppression.
MAX_PROTECTED_STEPS = 50


def _label(obj) -> str:
    return str(obj)[:300]


def _kind(obj) -> str:
    return str(obj._meta.verbose_name)


def _by_model(objects) -> list[list]:
    """Les lignes regroupées par modèle : Django ne rassemble qu'un modèle à la fois."""
    groups: dict[type, list] = {}
    for obj in objects:
        groups.setdefault(type(obj), []).append(obj)
    return list(groups.values())


def _take(roots: list, user, include_protected: bool) -> dict:
    """Copie puis supprime `roots` et ce qui part avec eux ; renvoie la copie (`payload`).

    Avec `include_protected`, les lignes qui protègent l'élément (imports de dossiers et leur
    traçabilité, fichiers source d'un scan…) partent aussi à la corbeille, AVANT lui : Django
    refuse de rassembler un élément tant qu'une ligne le protège en base, même si elle est
    promise à la suppression. On traite donc une pile de groupes d'un seul modèle : un groupe
    protégé attend que ceux qui le protègent soient partis. (Jusqu'à la 1.3.1, tout était
    rassemblé d'un coup, modèles mélangés : erreur 500 dès qu'un import de dossier était rattaché
    à la fiche.)
    """
    using = router.db_for_write(type(roots[0]))
    taken: list[dict] = []
    pending = [roots]
    for _ in range(MAX_PROTECTED_STEPS):
        if not pending:
            # L'élément d'abord, ce qui le protégeait ensuite : l'ordre de la restauration.
            taken.reverse()
            return {
                "objects": [row for part in taken for row in part["objects"]],
                "updates": [row for part in taken for row in part["updates"]],
            }
        group = pending[-1]
        model = type(group[0])
        # Une ligne déjà partie avec un groupe précédent (cascade) n'est pas copiée deux fois.
        alive = set(
            model._base_manager.using(using)
            .filter(pk__in=[o.pk for o in group])
            .values_list("pk", flat=True)
        )
        group = [o for o in group if o.pk in alive]
        if not group:
            pending.pop()
            continue
        collector = Collector(using=using)
        try:
            collector.collect(group)
        except ProtectedError as error:
            if not include_protected:
                raise
            pending[-1] = group
            pending.extend(_by_model(error.protected_objects))
            continue
        taken.append(_snapshot(collector))
        if user is not None:
            for objs in collector.data.values():
                for row in objs:
                    row._history_user = user  # l'historique dit qui a supprimé
        collector.delete()
        pending.pop()
    raise ValidationError("Suppression impossible : trop de liens à suivre.")


def _snapshot(collector: Collector) -> dict:
    instances = []
    for objs in collector.data.values():
        instances.extend(objs)
    for queryset in collector.fast_deletes:
        instances.extend(queryset)
    updates = []
    for (field, _value), targets in collector.field_updates.items():
        for target in targets:
            # Un queryset, une liste d'objets ou un objet seul selon la version de Django.
            several = hasattr(target, "model") or isinstance(target, (list, tuple))
            rows = target if several else [target]
            for row in rows:
                old = _json(getattr(row, field.attname))
                updates.append([row._meta.label, str(row.pk), field.attname, old])
    return {
        "objects": json.loads(serializers.serialize("json", instances)),
        "updates": updates,
    }


def _json(value):
    return value if value is None or isinstance(value, (int, float, bool)) else str(value)


def move_to_trash(
    obj,
    *,
    user=None,
    kind: str | None = None,
    label: str | None = None,
    country: str = "",
    reason: str = "",
    include_protected: bool = False,
) -> TrashEntry:
    """Met `obj` (et ce qui part avec lui) à la corbeille, puis le supprime."""
    # Relevés avant la suppression : Django vide l'identifiant de l'objet supprimé.
    described = {
        "label": (label or _label(obj))[:300],
        "kind": (kind or _kind(obj))[:100],
        "model": obj._meta.label,
        "object_id": str(obj.pk),
    }
    with transaction.atomic():
        payload = _take([obj], user, include_protected)
        entry = TrashEntry.objects.create(
            **described,
            country=country,
            reason=reason[:300],
            payload=payload,
            deleted_by=user if getattr(user, "pk", None) else None,
        )
    return entry


def restore(entry: TrashEntry, *, user=None) -> list:
    """Remet les lignes de `entry` à l'identique ; refuse si un élément les a remplacées."""
    if entry.restored_at:
        raise ValidationError("Cet élément a déjà été restauré.")
    try:
        with transaction.atomic():
            restored = []
            rows = json.dumps(entry.payload["objects"])
            for deserialized in serializers.deserialize("json", rows):
                for prepare in TRASH_PREPARE:
                    prepare(deserialized.object)
                deserialized.save()
                restored.append(deserialized.object)
            for label, pk, attname, value in entry.payload.get("updates", []):
                model = apps.get_model(label)
                model._base_manager.filter(pk=pk).update(**{attname: value})
            entry.restored_at = timezone.now()
            entry.restored_by = user if getattr(user, "pk", None) else None
            entry.save(update_fields=["restored_at", "restored_by"])
            for hook in TRASH_RESTORED:
                hook(entry, restored, user)
    except IntegrityError as error:
        raise ValidationError(
            "Restauration impossible : un élément équivalent existe déjà (par exemple la même "
            "AMM recréée depuis). Supprimez ou fusionnez-le d'abord."
        ) from error
    return restored


def trashed_files() -> set[str]:
    """Fichiers des éléments à la corbeille : ils restent au stockage (contrôle d'intégrité)."""
    names: set[str] = set()
    file_fields: dict[str, list[str]] = {}
    for payload in TrashEntry.objects.filter(restored_at__isnull=True).values_list(
        "payload", flat=True
    ):
        for row in payload.get("objects", []):
            label = row.get("model", "")
            if label not in file_fields:
                try:
                    model = apps.get_model(label)
                except LookupError:
                    file_fields[label] = []
                    continue
                file_fields[label] = [
                    f.name for f in model._meta.concrete_fields if isinstance(f, FileField)
                ]
            for field in file_fields[label]:
                name = row.get("fields", {}).get(field)
                if name:
                    names.add(name)
    return names


def trashed_entry(model, pk, *, user=None) -> TrashEntry | None:
    """L'entrée de corbeille (non restaurée) de cet élément, s'il y est déjà.

    Sert à rendre les suppressions idempotentes : supprimer deux fois ne lève pas d'erreur. Avec
    `user`, une entrée d'un pays hors de son périmètre n'est pas renvoyée.
    """
    label = model if isinstance(model, str) else model._meta.label
    entry = (
        TrashEntry.objects.filter(model=label, object_id=str(pk), restored_at__isnull=True)
        .order_by("-deleted_at")
        .first()
    )
    if entry is None or user is None or getattr(user, "is_global", True) or not entry.country:
        return entry
    countries = set(user.countries.values_list("iso2", flat=True))
    return entry if entry.country in countries else None


def trashed_values(model, *fields: str) -> set[tuple]:
    """Les valeurs de `fields` des lignes de `model` à la corbeille (non restaurées), en texte.

    Par exemple `trashed_values(MarketingAuthorization, "product", "country")` : les couples
    produit × pays des AMM supprimées. Les imports ne recréent pas ce qui a été supprimé.
    """
    label = (model if isinstance(model, str) else model._meta.label).lower()

    def text(value):
        return None if value is None else str(value)

    found: set[tuple] = set()
    payloads = TrashEntry.objects.filter(
        restored_at__isnull=True, payload__objects__contains=[{"model": label}]
    ).values_list("payload", flat=True)
    for payload in payloads:
        for row in payload.get("objects", []):
            if row.get("model", "").lower() == label:
                values = row.get("fields", {})
                found.add(tuple(text(values.get(field)) for field in fields))
    return found


def is_trashed(model, **match) -> bool:
    """Un élément de `model` répondant à `match` (par exemple `product=…, country=…`) est à la
    corbeille, non restauré."""
    wanted = tuple(None if value is None else str(value) for value in match.values())
    return wanted in trashed_values(model, *match.keys())


class IdempotentDestroyMixin:
    """Pour une vue DRF : supprimer un élément déjà supprimé (déjà à la corbeille) réussit.

    Un double clic, un onglet en retard ou une requête rejouée ne montrent jamais d'erreur :
    « quand on supprime, on supprime ». L'en-tête `X-Trash-Entry` donne l'entrée de corbeille,
    pour annuler (restaurer) ; il est absent quand l'élément n'est pas à la corbeille (scan
    archivé, pièce désactivée).
    """

    def destroy(self, request, *args, **kwargs):
        from django.http import Http404
        from rest_framework import status
        from rest_framework.response import Response

        lookup = self.lookup_url_kwarg or self.lookup_field
        try:
            instance = self.get_object()
        except Http404:
            model = self.get_queryset().model
            entry = trashed_entry(model, kwargs.get(lookup), user=request.user)
            if entry is None:
                raise
            response = Response(status=status.HTTP_204_NO_CONTENT)
            response["X-Trash-Entry"] = str(entry.pk)
            return response
        self.trash_entry = None
        self.perform_destroy(instance)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        if getattr(self, "trash_entry", None) is not None:
            response["X-Trash-Entry"] = str(self.trash_entry.pk)
        return response


class TrashDestroyMixin(IdempotentDestroyMixin):
    """Pour une vue DRF : DELETE met à la corbeille au lieu d'effacer.

    `trash_include_protected` : faire suivre les lignes qui protègent l'élément (une AMM et ses
    imports de dossiers). Sinon, un élément encore utilisé est refusé avec un message clair.
    """

    trash_include_protected = False

    def trash_country(self, instance) -> str:
        return ""

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError as DrfValidationError

        try:
            self.trash_entry = move_to_trash(
                instance,
                user=self.request.user,
                country=self.trash_country(instance),
                include_protected=self.trash_include_protected,
            )
        except ProtectedError as error:
            used = sorted({str(o._meta.verbose_name_plural) for o in error.protected_objects})
            raise DrfValidationError(
                {"detail": f"Encore utilisé ({', '.join(used)}) : impossible de le supprimer."}
            ) from error
