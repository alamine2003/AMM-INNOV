"""Flattened change history of an AMM (AMM itself, renewals and documents) via diff_against."""

from typing import Any

from .extensions import HISTORY_SOURCES

EXCLUDED = {"updated_at", "created_at"}


def label_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def entries_for_model(instances_history, model_label: str) -> list[dict]:
    """Builds history entries from a queryset of historical records ordered by history_date."""
    records = list(
        instances_history.select_related("history_user").order_by("history_date", "history_id")
    )
    entries: list[dict] = []
    previous_by_object: dict = {}
    for record in records:
        object_id = str(record.instance.pk)
        previous = previous_by_object.get(object_id)
        changes: list[dict] = []
        if record.history_type == "~" and previous is not None:
            delta = record.diff_against(previous, excluded_fields=EXCLUDED)
            changes = [
                {
                    "field": change.field,
                    "old": label_value(change.old),
                    "new": label_value(change.new),
                }
                for change in delta.changes
            ]
        elif record.history_type in ("+", "-"):
            # Une suppression est l'inverse d'une création : on liste ce qui disparaît.
            created = record.history_type == "+"
            changes = [
                {
                    "field": field.name,
                    "old": None if created else label_value(getattr(record, field.name)),
                    "new": label_value(getattr(record, field.name)) if created else None,
                }
                for field in record.instance._meta.fields
                if field.name not in EXCLUDED
                and field.name != "id"
                and getattr(record, field.name) not in (None, "", False)
            ]
        previous_by_object[object_id] = record
        if record.history_type == "~" and not changes:
            continue
        entries.append(
            {
                "date": record.history_date,
                "user_email": record.history_user.email if record.history_user else None,
                "type": {"+": "created", "~": "updated", "-": "deleted"}[record.history_type],
                "model": model_label,
                "object_id": object_id,
                "changes": changes,
            }
        )
    return entries


def amm_history(amm) -> list[dict]:
    from apps.amm.models import MarketingAuthorization, Renewal
    from apps.documents.models import Document
    entries = entries_for_model(MarketingAuthorization.history.filter(id=amm.pk), "amm")
    entries += entries_for_model(Renewal.history.filter(amm_id=amm.pk), "renewal")
    entries += entries_for_model(Document.history.filter(amm_id=amm.pk), "document")
    for source in HISTORY_SOURCES:  # corrections des imports de dossiers (apps/imports/hooks.py)
        entries += source(amm)
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries
