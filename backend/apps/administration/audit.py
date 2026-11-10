"""Audit et traçabilité : qui a fait quoi, quand, dans toute l'application.

Rien de nouveau n'est enregistré : l'audit relit ce qui existe déjà.

- L'historique (`simple_history`) de chaque modèle suivi : créations et modifications, avec
  l'auteur, la date, le motif et les champs changés. Les modèles sont découverts au démarrage :
  un modèle qui reçoit `history = HistoricalRecords()` apparaît ici sans autre changement.
- La corbeille (`TrashEntry`) : chaque suppression (avec ce qui partait avec l'élément) et
  chaque restauration. Les lignes « supprimé » de l'historique ne sont pas reprises : la
  corbeille les résume déjà, avec les lignes liées.

Les sources sont lues triées par date puis fusionnées ; une page de `size` événements lit au
plus `page × size` lignes par source.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from datetime import date, datetime, time

from django.apps import apps
from django.db.models import ForeignKey, Q
from django.utils import timezone

from apps.accounts.models import LOGIN_REASON
from apps.core.models import TrashEntry

CREATED = "created"
UPDATED = "updated"
DELETED = "deleted"
RESTORED = "restored"
LOGIN = "login"

ACTION_LABELS = {
    CREATED: "Création",
    UPDATED: "Modification",
    LOGIN: "Connexion",
    DELETED: "Mise à la corbeille",
    RESTORED: "Restauration",
}
HISTORY_TYPES = {"+": CREATED, "~": UPDATED}
MAX_CHANGES = 12


@dataclass
class Filters:
    user: str | None = None
    model: str | None = None
    action: str | None = None
    country: str | None = None
    since: date | None = None
    until: date | None = None
    # Utilisateur pays : seulement les éléments de ses pays (None = tout voir).
    scope: list[str] | None = None


def tracked_models() -> list:
    """Modèles avec un historique, triés par libellé."""
    models = [
        model
        for model in apps.get_models()
        if getattr(model._meta, "simple_history_manager_attribute", None)
    ]
    return sorted(models, key=lambda m: str(m._meta.verbose_name))


def model_types() -> list[dict]:
    """Types proposés dans le filtre : modèles suivis et tout ce que la corbeille a reçu."""
    types = {model._meta.label: _type_label(model) for model in tracked_models()}
    for label, kind in TrashEntry.objects.values_list("model", "kind").distinct():
        types.setdefault(label, kind[:1].upper() + kind[1:])
    return [
        {"value": value, "label": label} for value, label in sorted(types.items(), key=_by_label)
    ]


def _by_label(item):
    return item[1].lower()


def _type_label(model) -> str:
    name = str(model._meta.verbose_name)
    return name[:1].upper() + name[1:]


def _country_path(model) -> str | None:
    """Chemin vers le code pays de la ligne, s'il existe."""
    names = {field.name for field in model._meta.fields}
    if model._meta.label == "catalog.Country":
        return "iso2"
    if "country" in names:
        return "country__iso2"
    if "amm" in names:
        return "amm__country__iso2"
    return None


def _bounds(filters: Filters):
    tz = timezone.get_current_timezone()
    since = datetime.combine(filters.since, time.min, tz) if filters.since else None
    until = datetime.combine(filters.until, time.max, tz) if filters.until else None
    return since, until


def _history_queryset(model, filters: Filters):
    if filters.model and filters.model != model._meta.label:
        return None
    wanted = [k for k, v in HISTORY_TYPES.items() if not filters.action or v == filters.action]
    if filters.action == LOGIN:
        if model._meta.label != "accounts.User":
            return None
        wanted = ["~"]
    if not wanted:
        return None
    path = _country_path(model)
    if (filters.country or filters.scope is not None) and path is None:
        return None
    queryset = model.history.model.objects.filter(history_type__in=wanted)
    if model._meta.label == "accounts.User":
        if filters.action == LOGIN:
            queryset = queryset.filter(history_change_reason=LOGIN_REASON)
        elif filters.action == UPDATED:
            queryset = queryset.exclude(history_change_reason=LOGIN_REASON)
    if filters.user and model._meta.label == "accounts.User":
        # Une connexion n'a pas d'auteur dans l'historique : c'est la personne elle-même.
        queryset = queryset.filter(
            Q(history_user_id=filters.user) | Q(id=filters.user, history_user__isnull=True)
        )
    elif filters.user:
        queryset = queryset.filter(history_user_id=filters.user)
    since, until = _bounds(filters)
    if since:
        queryset = queryset.filter(history_date__gte=since)
    if until:
        queryset = queryset.filter(history_date__lte=until)
    if filters.country:
        queryset = queryset.filter(**{path: filters.country.upper()})
    if filters.scope is not None:
        queryset = queryset.filter(**{f"{path}__in": filters.scope})
    related = ["history_user"]
    if path and "__" in path:
        related.append(path.rsplit("__", 1)[0])
    return queryset.select_related(*related).order_by("-history_date", "-history_id")


def _trash_querysets(filters: Filters):
    """(action, queryset, champ date) pour les suppressions et les restaurations."""
    for action, date_field, user_field in (
        (DELETED, "deleted_at", "deleted_by"),
        (RESTORED, "restored_at", "restored_by"),
    ):
        if filters.action and filters.action != action:
            continue
        queryset = TrashEntry.objects.filter(**{f"{date_field}__isnull": False})
        if filters.model:
            queryset = queryset.filter(model=filters.model)
        if filters.user:
            queryset = queryset.filter(**{f"{user_field}_id": filters.user})
        since, until = _bounds(filters)
        if since:
            queryset = queryset.filter(**{f"{date_field}__gte": since})
        if until:
            queryset = queryset.filter(**{f"{date_field}__lte": until})
        if filters.country:
            queryset = queryset.filter(country=filters.country.upper())
        if filters.scope is not None:
            queryset = queryset.filter(country__in=filters.scope)
        yield (
            action,
            queryset.select_related(user_field).order_by(f"-{date_field}", "-id"),
            (
                date_field,
                user_field,
            ),
        )


def _sources(filters: Filters):
    for model in tracked_models():
        queryset = _history_queryset(model, filters)
        if queryset is not None:
            yield ("history", model), queryset
    for action, queryset, fields in _trash_querysets(filters):
        yield ("trash", action, fields), queryset


def _person(user) -> str | None:
    return user.full_name if user else None


def _country_of(row, path: str | None) -> str:
    if not path:
        return ""
    value = row
    try:
        for part in path.split("__"):
            value = getattr(value, part)
            if value is None:
                return ""
    except Exception:  # ligne liée supprimée depuis
        return ""
    return str(value)


def _label_of(row, model) -> str:
    try:
        return str(row.instance)[:300]
    except Exception:  # lien vers une ligne supprimée depuis
        return f"{_type_label(model)} {getattr(row, model._meta.pk.attname, '')}"


def _display(field, value):
    if value is None or value == "":
        return None
    if field is not None and field.choices:
        return str(dict(field.flatchoices).get(value, value))
    if isinstance(value, bool):
        return "oui" if value else "non"
    return str(value)[:200]


def _changes(row, model) -> list[dict]:
    previous = row.prev_record
    if previous is None:
        return []
    try:
        delta = row.diff_against(previous)
    except Exception:
        return []
    fields = {field.name: field for field in model._meta.fields}
    changes = []
    for change in delta.changes[:MAX_CHANGES]:
        field = fields.get(change.field)
        name = str(field.verbose_name) if field is not None else change.field
        if isinstance(field, ForeignKey):
            # Un identifiant ne dit rien à l'utilisateur : seulement le champ changé.
            changes.append({"field": name, "old": None, "new": None})
            continue
        changes.append(
            {
                "field": name,
                "old": _display(field, change.old),
                "new": _display(field, change.new),
            }
        )
    return changes


def _history_event(row, model) -> dict:
    action = HISTORY_TYPES[row.history_type]
    changes = _changes(row, model) if action == UPDATED else []
    user = row.history_user
    reason = row.history_change_reason or ""
    if model._meta.label == "accounts.User" and action == UPDATED and reason == LOGIN_REASON:
        action, changes, reason = LOGIN, [], ""
        user = user or row.instance  # la personne s'est connectée elle-même
    return {
        "id": f"{model._meta.label}:{row.history_id}",
        "at": row.history_date,
        "action": action,
        "action_label": ACTION_LABELS[action],
        "user": _person(user),
        "user_id": str(user.pk) if user else None,
        "model": model._meta.label,
        "type": _type_label(model),
        "object_id": str(getattr(row, model._meta.pk.attname)),
        "label": _label_of(row, model),
        "country": _country_of(row, _country_path(model)),
        "reason": reason,
        "changes": changes,
        "rows": 1,
    }


def _trash_event(entry: TrashEntry, action: str, fields) -> dict:
    date_field, user_field = fields
    user = getattr(entry, user_field)
    return {
        "id": f"trash:{action}:{entry.pk}",
        "at": getattr(entry, date_field),
        "action": action,
        "action_label": ACTION_LABELS[action],
        "user": _person(user),
        "user_id": str(user.pk) if user else None,
        "model": entry.model,
        "type": entry.kind[:1].upper() + entry.kind[1:],
        "object_id": entry.object_id,
        "label": entry.label,
        "country": entry.country,
        "reason": entry.reason if action == DELETED else "",
        "changes": [],
        "rows": len(entry.payload.get("objects", [])),
    }


def events(filters: Filters, page: int, size: int) -> tuple[int, list[dict]]:
    """(nombre total d'événements, événements de la page), du plus récent au plus ancien."""
    window = page * size
    count = 0
    streams = []
    for source, queryset in _sources(filters):
        count += queryset.count()
        rows = list(queryset[:window])
        if source[0] == "history":
            model = source[1]
            dated = [(row.history_date, ("history", model, row)) for row in rows]
        else:
            _, action, fields = source
            dated = [(getattr(row, fields[0]), ("trash", action, fields, row)) for row in rows]
        streams.append(dated)
    merged = heapq.merge(*streams, key=lambda item: item[0], reverse=True)
    selected = [item for _, item in list(merged)[(page - 1) * size : window]]
    result = []
    for item in selected:
        if item[0] == "history":
            result.append(_history_event(item[2], item[1]))
        else:
            result.append(_trash_event(item[3], item[1], item[2]))
    return count, result


def people() -> list[dict]:
    """Personnes proposées dans le filtre (tous les comptes, y compris désactivés)."""
    from apps.accounts.models import User

    return [
        {"id": str(user.pk), "name": user.full_name, "active": user.is_active}
        for user in User.objects.order_by("first_name", "last_name", "email")
    ]
