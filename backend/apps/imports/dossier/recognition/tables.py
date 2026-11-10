"""Tableaux des recueils de décisions : une ligne par présentation (n°, date, libellé)."""

import re
from datetime import date

from .dates import _MONTH_NAMES
from .text import fold, normalize

_CODED_NUMBER = r"\b((?:E|MD)\s?[-/]\s?\d{4,6}\s?[-/]\s?\d{3,5})\b"  # E-2015-1669, MD/201924/0459
_TRAILING_NUMBER = r"(?<![\d,.'/])(\d{3} \d{3}|\d{4,6})\s*\|?\s*$"  # « … B/30 12,0€ 5879 »
_DATED_NUMBER = (
    r"(?<![\d,.'/])(\d{4,6})\s+(?=\d{1,2}/\d{1,2}/\d{4}(?:\s+\d{1,2}/\d{1,2}/\d{4})?\s*\|?\s*$)"
)
_ROW_DATE = r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?!\d)"
_PRESENTATION = re.compile(
    r"\d\s*(?:mg|g|ml|%|mcg|ui)\b|\bb\s*/\s*\d|\b(?:comprim|cpr|gel|g[ée]lule|sirop|susp|inj|sol"
    r"|pdre|poudre|sach|tablet|capsule|syrup|cr[eè]me|pommade|collyre|ovule|suppo|fl\b)",
    re.I,
)


def _row_date(value: str) -> str | None:
    match = re.search(_ROW_DATE, value)
    if not match:
        return None
    day, month, year = int(match[1]), int(match[2]), int(match[3])
    if year < 100:
        year += 2000 if year < 70 else 1900
    try:
        return date(year, month, day).isoformat() if 1950 <= year <= 2150 else None
    except ValueError:
        return None


def _clean_label(value: str) -> str:
    value = re.sub(r"^\s*[\[(]?\d{1,3}\s*[\]).:_|-]*\s+", "", value)  # numéro de ligne
    value = re.sub(r"\d+(?:[.,]\d+)*\s*(?:€|eur|euros|fcfa|f cfa)", " ", value, flags=re.I)
    return re.sub(r"\s+", " ", re.sub(r"[|_]+", " ", value)).strip(" .;:-|")


_GENERIC_WORDS = {
    "comprime", "comprimes", "pellicule", "pellicules", "secable", "secables", "enrobe",
    "enrobes", "boite", "boites", "gelule", "gelules", "sirop", "flacon", "flacons", "sachet",
    "sachets", "suspension", "buvable", "injectable", "solution", "poudre", "ampoule",
    "ampoules", "effervescent", "effervescents", "creme", "pommade", "collyre", "gouttes",
    "tube", "de", "du", "des", "la", "le", "les", "pour", "et", "en", "mg", "ml", "unite",
}  # fmt: skip


def _generic_label(label: str) -> bool:
    """Le libellé ne dit que la forme et le conditionnement (« comprimés pelliculés »)."""
    words = [word for word in normalize(label).split() if not word.isdigit()]
    return bool(words) and all(word in _GENERIC_WORDS or len(word) <= 2 for word in words)


def _label_above(lines: list[str], index: int, label: str) -> str:
    """Remonte jusqu'à la ligne qui porte la marque (premier mot en capitales)."""
    parts = [label]
    for previous in reversed(lines[max(0, index - 3) : index]):
        if not previous.strip():
            continue
        if re.search(_CODED_NUMBER, previous) or re.search(
            r"denomination|designation|n.\s*de\s+visa|delivrance", fold(previous)
        ):
            break
        parts.insert(0, _clean_label(previous))
        first = re.search(r"[A-Za-zÀ-ÿ]{3,}", previous)
        if first and first.group().isupper() and normalize(first.group()) not in _GENERIC_WORDS:
            break
    return " ".join(part for part in parts if part)


def table_rows(text: str) -> list[dict]:
    """Lignes « produit → n° d'AMM (→ date) » d'une décision groupée ; [] s'il n'y a pas de tableau.

    L'OCR restitue un tableau soit ligne par ligne, soit colonne par colonne (dénomination, puis
    numéro, puis date sur des lignes successives) : la dénomination est alors la ligne précédente.
    """
    lines = text.splitlines()
    rows = []
    for index, line in enumerate(lines):
        coded = re.search(_CODED_NUMBER, line)
        # Guinée : « … 5 EURO 6261 10/09/2025 10/09/2030 » (numéro, début, fin en fin de ligne).
        trailing = (
            None if coded else (re.search(_TRAILING_NUMBER, line) or re.search(_DATED_NUMBER, line))
        )
        found = coded or trailing
        if not found or re.match(r"\s*[-•]?\s*vu\b", fold(line)):
            continue
        number = found.group(1)
        label = _clean_label(line[: found.start()])
        if trailing and (
            not _PRESENTATION.search(label)
            or re.search(r"(?:" + _MONTH_NAMES + r")\.?\s*$", fold(label))
        ):
            continue
        if sum(character.isalpha() for character in label) >= 4 and _generic_label(label):
            # Côte d'Ivoire : « AMLO VH 5 mg/12,5 mg/160 mg Amlodipine, » puis, ligne suivante,
            # « comprimés pelliculés E-2015-418 | 29/07/2015 » : la dénomination est au-dessus.
            label = _label_above(lines, index, label)
        if sum(character.isalpha() for character in label) < 4:
            for previous in reversed(lines[max(0, index - 3) : index]):
                candidate = _clean_label(previous)
                if (
                    sum(character.isalpha() for character in candidate) >= 4
                    and not re.search(_CODED_NUMBER, previous)
                    and not re.search(r"denomination|designation|n.\s*de\s+visa", fold(previous))
                ):
                    label = candidate
                    break
            else:
                continue
        after = line[found.end() :] + "\n" + "\n".join(lines[index + 1 : index + 3])
        rows.append(
            {
                "label": label[:160],
                "number": number,
                # La date suit le numéro, sur la ligne ou juste après, avant le numéro suivant.
                "date": _row_date(re.split(_CODED_NUMBER, after)[0]),
            }
        )
    if len(rows) < 3:
        return []
    # Côte d'Ivoire : tous les visas d'une même liste portent la date de la séance ; une date
    # décalée par l'OCR (au-dessus de la dénomination) est celle des autres lignes.
    dates = {row["date"] for row in rows if row["date"]}
    if len(dates) == 1 and sum(1 for row in rows if row["date"]) >= 2:
        for row in rows:
            row["date"] = row["date"] or next(iter(dates))
    return rows


