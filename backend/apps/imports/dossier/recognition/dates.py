"""Dates d'une décision : dates écrites en lettres ou en chiffres, dates lues par OCR,
validité imprimée (« cinq (5) ans »)."""

import re
import unicodedata
from datetime import date

MONTHS = {
    "janvier": 1,
    "january": 1,
    "fevrier": 2,
    "february": 2,
    "mars": 3,
    "march": 3,
    "avril": 4,
    "april": 4,
    "mai": 5,
    "may": 5,
    "juin": 6,
    "june": 6,
    "juillet": 7,
    "july": 7,
    "aout": 8,
    "august": 8,
    "septembre": 9,
    "september": 9,
    "octobre": 10,
    "october": 10,
    "novembre": 11,
    "november": 11,
    "decembre": 12,
    "december": 12,
}
# Abréviations imprimées sur les décisions (« 16 AVR 2019 », « 09 Déc. 2019 », « 24 SEP 2020 »).
MONTH_ABBREVIATIONS = {
    "janv": 1, "jan": 1, "fevr": 2, "fev": 2, "feb": 2, "avr": 4, "apr": 4, "juil": 7,
    "jul": 7, "jun": 6, "aou": 8, "aug": 8, "sept": 9, "sep": 9, "oct": 10, "nov": 11,
    "dec": 12,
}  # fmt: skip
ALL_MONTHS = {**MONTHS, **MONTH_ABBREVIATIONS}
_MONTH_NAMES = "|".join(sorted(ALL_MONTHS, key=len, reverse=True))
# « 1er juin 2020 », « 22nd July 2019 », « 22" July 2019 » (ordinal lu comme un guillemet).
_TEXT_DATE = (
    rf"(\d{{1,2}})(?:er|st|nd|rd|th|[\"'°º]{{1,2}}(?:nd|st|rd|th)?)?\.?\s*"
    rf"({_MONTH_NAMES})\b\.?,?\s+(\d{{4}})"
)
DATE_PATTERN = (
    r"(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"
    r"|\d{1,2}(?:er|st|nd|rd|th|[\"'°º]{1,2}(?:nd|st|rd|th)?)?\.?\s*(?:"
    + _MONTH_NAMES
    + r")\b\.?,?\s+\d{4})"
)


# Tampon dateur lu chiffre par chiffre : « Bamako, le 2 9 DEC 2023 », « COTONOU, le2 6 JUIN 2019 ».
# Le jour est recollé (« 2 9 » → « ␣29 ») à longueur égale : `plain` reste aligné sur le texte.
_SPACED_DAY = re.compile(rf"(?<!\d)(\d) (\d)(?=\s*\.?\s*(?:{_MONTH_NAMES})\b)")


def _join_spaced_days(plain: str) -> str:
    return _SPACED_DAY.sub(r" \1\2", plain)


def parse_date(value: str) -> str | None:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    match = re.search(DATE_PATTERN, plain)
    if not match:
        return None
    textual = re.fullmatch(_TEXT_DATE, match.group())
    parts = re.split(r"[-/.\s]+", match.group())
    try:
        if textual:
            day, month, year = int(textual[1]), ALL_MONTHS[textual[2]], int(textual[3])
        elif len(parts[0]) == 4:
            year, month, day = map(int, parts)
        else:
            day, month, year = map(int, parts)
        if not 1950 <= year <= 2150:
            return None
        return date(year, month, day).isoformat()
    except (ValueError, KeyError):
        return None


def _label_value(text: str, labels: str, source: str | None = None) -> str:
    """Valeur d'un champ étiqueté ; `source` (même longueur) fournit la casse d'origine."""
    match = re.search(rf"(?:^|\n)\s*(?:{labels})\s*(?::|=|\s[-–]\s)\s*([^\n]{{1,255}})", text, re.I)
    if not match:
        return ""
    original = source if source is not None and len(source) == len(text) else text
    return original[match.start(1) : match.end(1)].strip(" \t.;")


def _labeled_date(text: str, labels: str) -> str | None:
    match = re.search(rf"(?:{labels})\s*(?::|=|du|le)?\s*({DATE_PATTERN})", text, re.I)
    return parse_date(match.group(1)) if match else None


# OCR des scans : « du11/09/2018 », « dui1/09/2018 », « 11/o9/2018 ». Les lettres qui
# ressemblent à des chiffres ne sont corrigées qu'à l'intérieur d'une forme de date.
_OCR_DIGITS = str.maketrans({"o": "0", "i": "1", "l": "1", "|": "1"})
_TOLERANT_DATE = r"([0-9oil|]{1,2}\s?[-/.]\s?[0-9oil|]{1,2}\s?[-/.]\s?[0-9]{4})(?![0-9])"


def _tolerant_dates(text: str, labels: str) -> list[str]:
    """Toutes les dates lisibles qui suivent l'un des libellés, dans l'ordre du texte."""
    found = []
    for match in re.finditer(
        rf"(?:{labels})[ \t:]*(?:{_TOLERANT_DATE}|({DATE_PATTERN}))", text, re.I
    ):
        if match.group(2):  # date en toutes lettres (« à compter du 1er juin 2020 »)
            value = parse_date(match.group(2))
            if value:
                found.append(value)
            continue
        raw = match.group(1).translate(_OCR_DIGITS).replace(" ", "")
        if sum(character.isdigit() for character in match.group(1)) < 6:
            continue
        value = parse_date(raw)
        if value:
            found.append(value)
    return found


_NUMBER_WORDS = {
    "un": 1,
    "one": 1,
    "deux": 2,
    "two": 2,
    "trois": 3,
    "three": 3,
    "quatre": 4,
    "four": 4,
    "cinq": 5,
    "cing": 5,
    "five": 5,
    "six": 6,
    "dix": 10,
    "ten": 10,
    "douze": 12,
    "twelve": 12,
    "dix huit": 18,
    "eighteen": 18,
    "vingt quatre": 24,
    "twenty four": 24,
}


# Capitales où les décisions sont signées (« COTONOU, le … »).
_SIGNATURE_PLACES = (
    "cotonou|porto novo|ouagadougou|yaounde|brazzaville|abidjan|djibouti|libreville|banjul"
    "|conakry|bamako|nouakchott|niamey|dakar|n\\W?djamena|lome|antananarivo"
)


def _validity_months(plain: str) -> int | None:
    """Durée de validité imprimée (« cinq (5) ans », « eighteen (18) months »), en mois."""
    durations = set()
    for match in re.finditer(
        r"(?:validite|valid|valable|periode)[^\n]{0,90}?(?:\((\d{1,2})\s*[)a-z]?\s*"
        r"|\b(" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")\b[^\n(]{0,4}"
        r"(?:\(\s*[^\s)]{0,3}\s*\)?\s*)?)(ans|annees|years|mois|months)",
        plain,
    ):
        count = int(match.group(1)) if match.group(1) else _NUMBER_WORDS[match.group(2)]
        durations.add(count * (12 if match.group(3) in ("ans", "annees", "years") else 1))
    return durations.pop() if len(durations) == 1 else None


def _add_months(value: str, months: int) -> str:
    start = date.fromisoformat(value)
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    for day in (start.day, 30, 29, 28):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    return value


def _vote(values: list[str]) -> str | None:
    """La valeur lue le plus souvent ; une égalité entre lectures différentes reste indécise."""
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None
    ranked = sorted(counts.items(), key=lambda item: -item[1])
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _validity_period(plain: str) -> tuple[str | None, str | None]:
    """Début et fin de validité : « à partir du X … à renouveler au plus tard le Y »."""
    start = _vote(
        _tolerant_dates(
            plain,
            r"(?:a|4|&)?\s*(?:partir|compter|conipter)\s*(?:\(?\s*d[uiv]|\(gu)"
            r"|(?:years|months|ans|mois)\s+(?:from|frow|trom)\s*(?:the)?"
            r"|valid\s+(?:as\s+)?from\s*(?:the)?",
        )
    )
    ends = _tolerant_dates(
        plain,
        r"renouveler\s+(?:au|ou)\s+plus\s+tard\s+le|(?:renewed|sewed)\s+before"
        r"|valid\s+until|valable\s+jusqu['’ ]?au",
    )
    if start:
        ends = [value for value in ends if value > start]
    months = _validity_months(plain)
    if start and months:
        expected = date.fromisoformat(_add_months(start, months))
        # La date imprimée prime sur le calcul si elle lui correspond (18 mois : 22/01 → 24/07).
        close = [value for value in ends if abs((date.fromisoformat(value) - expected).days) <= 45]
        return start, _vote(close) or expected.isoformat()
    return start, _vote(ends)


