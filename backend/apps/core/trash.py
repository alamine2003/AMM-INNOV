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

MAX_PROTECTED_ROUNDS = 6


def _label(obj) -> str:
    return str(obj)[:300]


def _kind(obj) -> str:
    return str(obj._meta.verbose_name)


def _collect(roots: list, include_protected: bool) -> Collector:
    """Ce que la suppression emporterait. Avec `include_protected`, les lignes qui protègent
    l'élément (imports de dossiers…) partent aussi à la corbeille, avec lui."""
    using = router.db_for_write(type(roots[0]))
    for _ in range(MAX_PROTECTED_ROUNDS):
        collector = Collector(using=using)
        try:
            collector.collect(roots)
            return collector
        except ProtectedError as error:
            if not include_protected:
                raise
            known = {(type(o), o.pk) for o in roots}
            roots = [o for o in error.protected_objects if (type(o), o.pk) not in known] + roots
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
    with transaction.atomic():
        collector = _collect([obj], include_protected)
        entry = TrashEntry.objects.create(
            label=(label or _label(obj))[:300],
            kind=(kind or _kind(obj))[:100],
            model=obj._meta.label,
            object_id=str(obj.pk),
            country=country,
            reason=reason[:300],
            payload=_snapshot(collector),
            deleted_by=user if getattr(user, "pk", None) else None,
        )
        if user is not None:
            for objs in collector.data.values():
                for row in objs:
                    row._history_user = user  # l'historique dit qui a supprimé
        collector.delete()
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


class TrashDestroyMixin:
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
            move_to_trash(
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
