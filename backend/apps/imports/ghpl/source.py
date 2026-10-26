"""Le registre du classement AMM GHPL, lu comme le manifeste des scans.

Le manifeste `manifeste_scans_amm_gh.csv` a été tiré une fois du registre (13/10/2026) ; le
registre, lui, est réécrit à chaque passage de la tâche planifiée du classement. La
synchronisation en dérive donc elle-même les lignes du manifeste, avec les mêmes règles :

- une ligne de `_Docs` par pièce ; les copies (`_DOUBLONS`, `_PAGES SEPAREES`,
  `_DOCUMENT COMPLET`) ne sont pas des exemplaires principaux ;
- la période vient du type et du dossier de rangement (« RENOUVELLEMENTS > RENOUVELLEMENT 2 -
  2018-03-01 » → « RENOUVELLEMENT 2 ») ;
- le libellé du Dashboard vient de `_Consolidation` (présentation du Dashboard dont la
  présentation classée est celle de la pièce), s'il est unique.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime

from ..registry import COUNTRIES, _plain

COPIES = ("_DOUBLONS", "_PAGES SEPAREES", "_DOCUMENT COMPLET")
TYPES = {
    "AMM (OCTROI)": ("ORIGINE", "AMM"),
    "RENOUVELLEMENT": ("RENOUVELLEMENT", "AMM"),
    "DEPOT / ATTESTATION": ("DEPOT", "RECEPISSE"),
    "VARIATION / RECTIFICATIF": ("VARIATION", "COURRIER"),
    "RCP / ANNEXE": ("RCP", "AUTRE"),
    "AUTRE": ("DEPOT", "AUTRE"),
}
RENEWAL_FOLDER = re.compile(r"RENOUVELLEMENT (\d+)\b")
# Pays du classement non suivis par AMM GH : l'import les signale (« pays non suivi »).
ISO2 = {**COUNTRIES, "MAURITANIE": "MR", "RDC": "CD"}
# Champs du registre que l'import lit (le reste, « Jours », « Echeance »… change chaque jour).
REGISTRY_FIELDS = (
    "Pays",
    "Gamme",
    "Presentation",
    "Referentiel",
    "Source",
    "Controle",
    "N° AMM origine",
    "Date origine",
    "Statut dossier",
)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


EXCEL_EPOCH = datetime(1899, 12, 30)


def doc_date(value) -> str:
    """Date d'une pièce. Une année seule (2026), mise en forme de date dans Excel, s'y lit
    1905-07-18 : on rend l'année, comme le manifeste (date approximative, ignorée à l'import)."""
    if isinstance(value, datetime) and value.year < 1910:
        serial = (value - EXCEL_EPOCH).days
        return str(serial) if 1900 <= serial <= 2100 else ""
    return _text(value)[:10]


def is_principal(path: str) -> bool:
    return not any(marker in path.upper() for marker in COPIES)


def period_of(doc_type: str, rangement: str) -> tuple[str, str]:
    period, kind = TYPES.get(_plain(doc_type), ("", "AUTRE"))
    if period == "RENOUVELLEMENT":
        match = RENEWAL_FOLDER.search(_plain(rangement))
        period = f"RENOUVELLEMENT {match.group(1)}" if match else ""
    return period, kind


def dashboard_labels(records: list[dict]) -> dict[tuple[str, str], str]:
    """(pays, présentation classée) → libellé du Dashboard, quand il n'y en a qu'un."""
    labels: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        classed = _text(record.get("Referentiel"))
        if classed and "DASHBOARD" in _plain(record.get("Source")):
            labels[(_plain(record.get("Pays")), _plain(classed))].add(
                _text(record.get("Presentation"))
            )
    return {key: next(iter(values)) for key, values in labels.items() if len(values) == 1}


def manifest_rows(docs: list[dict], records: list[dict]) -> list[dict]:
    """Lignes au format de `scans._read` (clés courtes), une par pièce du registre."""
    labels = dashboard_labels(records)
    rows = []
    for line, doc in enumerate(docs, start=2):
        path = _text(doc.get("Chemin")).replace("\\", "/")
        if not path:
            continue
        country = _plain(doc.get("Pays"))
        presentation = _text(doc.get("Presentation"))
        period, kind = period_of(_text(doc.get("Type")), _text(doc.get("Rangement")))
        rows.append(
            {
                "pays": _text(doc.get("Pays")),
                "iso2": ISO2.get(country, ""),
                "gamme": _text(doc.get("Gamme")),
                "presentation": presentation,
                "libelle": labels.get((country, _plain(presentation)), ""),
                "periode": period,
                "kind": kind,
                "date": doc_date(doc.get("Date")),
                "fiabilite": ""
                if _plain(doc.get("Fiabilite date")) == "NON LUE"
                else _text(doc.get("Fiabilite date")),
                "numero": _text(doc.get("N° AMM")),
                "principal": "oui" if is_principal(path) else "non",
                "chemin": path,
                "nom": _text(doc.get("Nom du fichier")) or path.rsplit("/", 1)[-1],
                "sha256": "",
                "line": line,
            }
        )
    return rows


def _digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()[:20]


def group_key(row: dict) -> str:
    return f"{row['iso2'].upper()}|{_plain(row['presentation'])}"


def record_key(record: dict) -> str:
    classed = _text(record.get("Referentiel")) or _text(record.get("Presentation"))
    return f"{_plain(record.get('Pays'))}|{_plain(classed)}|{_plain(record.get('Presentation'))}"


def fingerprints(rows: list[dict], records: list[dict], deposits: dict) -> dict[str, str]:
    """Empreinte de chaque présentation : pièces (D:) et ligne du registre (R:)."""
    groups: dict[str, list] = defaultdict(list)
    for row in rows:
        if row["principal"] == "oui":
            groups[group_key(row)].append(
                [
                    row[k]
                    for k in ("chemin", "periode", "kind", "date", "fiabilite", "numero", "libelle")
                ]
            )
    prints = {f"D:{key}": _digest(sorted(items)) for key, items in groups.items()}
    for record in records:
        key = record_key(record)
        deposit_key = (
            f"{_plain(record.get('Pays'))}|"
            f"{_plain(record.get('Referentiel') or record.get('Presentation'))}"
        )
        values = [_text(record.get(name)) for name in REGISTRY_FIELDS]
        values.append(_text(deposits.get(deposit_key)))
        prints[f"R:{key}"] = _digest(values)
    return prints
