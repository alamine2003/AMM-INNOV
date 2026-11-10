"""Ce que disent les scans d'un dossier : valeur retenue quand plusieurs scans la donnent
(consensus), points à vérifier, changements proposés, corrections d'après la décision."""

import hashlib
import re
from collections import defaultdict

from .labels import FIELD_LABELS, period_label, show
from .recognition import normalize


def _consensus(rows, fields, points, label):
    values, proofs, confidences = {}, {}, {}
    for field in fields:
        evidence = [row for row in rows if row["official"] and row.get(field)]
        variants = {normalize(str(row[field])) for row in evidence}
        if len(variants) > 1:
            readings = ", ".join(sorted({show(field, row[field]) for row in evidence})[:3])
            name = FIELD_LABELS.get(
                f"original_{field}" if label == "AMM d'origine" else field,
                FIELD_LABELS.get(field, field),
            )
            _point(
                points,
                "contradiction",
                f"{label} : les décisions du dossier se contredisent ({name} : {readings}) ; "
                "valeur non reprise.",
            )
            continue
        if evidence:
            chosen = max(evidence, key=lambda row: (row["confidence"], row["file_id"]))
            values[field], proofs[field] = chosen[field], chosen["file_id"]
            confidences[field] = chosen["confidence"]
    return values, proofs, confidences


def _point(
    points,
    code,
    message,
    *,
    target=None,
    field="",
    recorded=None,
    scan=None,
    proof=None,
    confidence=0,
):
    points.append(
        {
            "code": code,
            "message": message,
            "target": target,
            "field": field,
            "recorded": recorded,
            "scan": scan,
            "proof_file_id": str(proof) if proof else None,
            "confidence": confidence,
        }
    )


def _change(target, field, old, new, proof, confidence, *, replaces=None):
    """Une différence scan / fiche. Champ vide : complété d'office ; sinon point à vérifier."""
    if hasattr(old, "isoformat"):
        old = old.isoformat()
    if old == new or (not old and not new):
        return None
    same_number = field in {"original_number", "number"} and old and new
    if same_number and number_key(old) == number_key(new):
        return None  # « E-2015-0418 » (fiche) et « E-2015- 418 » (scan) : le même numéro
    identity = f"{target}:{field}:{proof}:{new}"
    return {
        "id": hashlib.sha256(identity.encode()).hexdigest()[:24],
        "target": target,
        "field": field,
        "old": old,
        "new": new,
        "proof_file_id": proof,
        "confidence": confidence,
        # Jamais d'écrasement automatique d'une valeur renseignée : elle devient un point.
        "requires_confirmation": bool(old not in (None, "")) if replaces is None else replaces,
    }


# Champs qu'une décision officielle lisible corrige d'office (classement autonome).
CORRECTABLE = {
    "original_number",
    "original_start_date",
    "original_end_date",
    "holder",
    "number",
    "start_date",
    "end_date",
    "decision_date",
}
CORRECTION_MIN_CONFIDENCE = 70


def _correct_from_scans(changes, rows, amm, renewals, decisions):
    """La décision officielle fait foi : l'écart scan ≠ fiche corrige la fiche.

    Seulement pour une lecture sûre : preuve officielle, lecture concordante (une contradiction
    entre décisions n'a déjà retenu aucune valeur), n° lu sans variante, PDF texte ou lecture OCR
    confirmée par une deuxième décision, et jamais une date de fin qui précéderait le début.
    L'ancienne valeur reste dans l'historique de la fiche et dans le récapitulatif ; sinon
    l'écart reste un point.
    """
    by_file = {row["file_id"]: row for row in rows}
    existing = {item["key"]: item for item in renewals if item.get("existing_id")}
    candidates = defaultdict(list)
    for change in changes:
        if not change["requires_confirmation"] or change["field"] not in CORRECTABLE:
            continue
        proof = by_file.get(str(change["proof_file_id"]))
        if not proof or not proof["official"] or change["confidence"] < CORRECTION_MIN_CONFIDENCE:
            continue
        if change["field"] in {"original_number", "number"} and proof.get("number_variants"):
            continue
        # Lecture OCR (fiabilité 80) : il faut une deuxième décision qui lise la même valeur.
        key = change["field"].removeprefix("original_")
        agreeing = {
            row["file_id"]
            for row in rows
            if row["official"]
            and row.get(key)
            and normalize(str(row[key])) == normalize(str(change["new"]))
        }
        if proof["confidence"] < 90 and len(agreeing) < 2:
            continue
        candidates[change["target"]].append(change)
    for target, proposals in candidates.items():
        values = {change["field"]: change["new"] for change in proposals}
        if target == "amm":
            start = values.get("original_start_date") or _iso(amm and amm.original_start_date)
            end = values.get("original_end_date") or _iso(amm and amm.original_end_date)
        else:
            if target not in existing:
                continue
            start = values.get("start_date") or existing[target].get("start_date")
            end = values.get("end_date") or existing[target].get("end_date")
        if start and end and str(end) < str(start):
            continue
        for change in proposals:
            change["requires_confirmation"] = False
            change["correction"] = True
            where = "AMM d'origine" if target == "amm" else period_label(target)
            _decision(
                decisions,
                f"{FIELD_LABELS.get(change['field'], change['field']).capitalize()} ({where}) "
                f"corrigé d'après la décision : « {show(change['field'], change['old'])} » → "
                f"« {show(change['field'], change['new'])} ».",
            )


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def number_key(value: str) -> str:
    """Numéro comparable : sans espaces ni zéros de tête (« E-2015-0418 » = « E-2015- 418 »)."""
    tokens = re.findall(r"[a-z]+|\d+", normalize(str(value)))
    return "-".join(token.lstrip("0") or "0" if token.isdigit() else token for token in tokens)


def _decision(decisions, message):
    """Décision prise seule par l'application, montrée dans le récapitulatif."""
    if message not in decisions:
        decisions.append(message)
