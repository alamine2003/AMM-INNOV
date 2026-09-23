"""Libellés en français simple des champs et des périodes d'une AMM (messages de l'import)."""

import re
from datetime import date

FIELD_LABELS = {
    "original_number": "N° d'AMM",
    "original_start_date": "date de délivrance",
    "original_end_date": "date d'échéance",
    "holder": "titulaire",
    "number": "n° de renouvellement",
    "start_date": "date de début",
    "end_date": "date de fin",
    "decision_date": "date de décision",
    "workflow_status": "statut du renouvellement",
}

WORKFLOW_LABELS = {
    "PLANIFIE": "planifié",
    "EN_PREPARATION": "en préparation",
    "DEPOSE": "déposé",
    "EN_INSTRUCTION": "en instruction",
    "OBTENU": "obtenu",
    "REJETE": "rejeté",
    "ABANDONNE": "abandonné",
}


def fr_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, date):
        value = value.isoformat()
    y, m, d = str(value)[:10].split("-")
    return f"{d}/{m}/{y}"


def show(field: str, value) -> str:
    """Valeur lisible : dates au format français, statuts traduits, « vide »."""
    if value in (None, ""):
        return "vide"
    if field.endswith("date"):
        return fr_date(value)
    if field == "workflow_status":
        return WORKFLOW_LABELS.get(str(value), str(value))
    return str(value)


def period_label(key: str, values: dict | None = None) -> str:
    """« AMM d'origine », « Renouvellement du 11/09/2018 » ; jamais la clé interne."""
    if key == "original":
        return "AMM d'origine"
    values = values or {}
    when = values.get("start_date") or values.get("decision_date")
    if not when:
        found = re.search(r"(\d{4}-\d{2}-\d{2})", key or "")
        when = found.group(1) if found else None
    if when:
        return f"Renouvellement du {fr_date(when)}"
    year = re.search(r"(?:^|\D)((?:19|20)\d{2})(?:\D|$)", key or "")
    return f"Renouvellement de {year.group(1)}" if year else "Renouvellement (date non lue)"
