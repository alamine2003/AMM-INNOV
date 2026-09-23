"""Conservative, explainable recognition of regulatory fields and dossier periods."""

import re
import unicodedata
from datetime import date
from pathlib import PurePosixPath


def fold(value: str) -> str:
    """Minuscules sans accents, à positions conservées : un caractère pour un caractère.

    Permet de chercher sans se soucier de la casse ni des accents tout en renvoyant la
    valeur telle qu'elle est imprimée sur la décision.
    """
    folded = []
    for character in value:
        ascii_form = unicodedata.normalize("NFKD", character).encode("ascii", "ignore").decode()
        candidate = (ascii_form[:1] or character).lower()
        folded.append(candidate[:1])
    return "".join(folded)


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


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


def _edit_distance(first: str, second: str) -> int:
    previous = list(range(len(second) + 1))
    for index, left in enumerate(first, 1):
        current = [index]
        for position, right in enumerate(second, 1):
            current.append(
                min(
                    previous[position] + 1,
                    current[-1] + 1,
                    previous[position - 1] + (left != right),
                )
            )
        previous = current
    return previous[-1]


# Un numéro peut contenir des espaces suivis de chiffres (« MCA/Med 025/03/19 », « 245 041 »,
# « SP.TG 5223 ») ; il s'arrête au premier mot (« 0003/CN/06/2019 du 09 Déc. 2019 »).
_NUMBER_TOKEN = r"([0-9a-z][0-9a-z/_.-]{0,40}(?:[ ](?=[0-9])[0-9a-z/_.-]{1,20}){0,2})"
# Chaque famille de mention est une lecture indépendante du même numéro : « Registration number »,
# la mention « AMM N° » française, sa traduction « Marketing Authorization No. », et la ligne
# « Décision N° » (qui, selon les pays, porte le numéro d'AMM ou un numéro d'acte distinct).
_NUMBER_SOURCES = {
    "registration": r"registration\s+(?:number|no\.?)\s*[:.]?\s*"
    r"|enregistre\w*\s+sous\s+le\s+n\S{0,2}\s*(?:amm[\s_:]*)?(?!/?\s*registration)",
    # « … est renouvelée sous le numéro 0374R/09/2020 », « Sous le numéro : 7897 » : le numéro
    # attribué par la décision, prioritaire sur l'ancien numéro qu'elle rappelle.
    "granted": r"sous\s+le\s+(?:numero|n[°º])\s*[:.]?\s*(?:amm[\s_:]*)?",
    "fr": r"(?:numero|n[°ºo.]*)\s*(?:d['’ ]*)?amm[\s_]*[:=]?[\s_]*"
    r"|(?:amm|autorisation de mise sur le marche)\s*(?:n[°ºo.*]*\s*|numero\s+)"
    r"|(?:n[°ºo.]*|numero)\s*(?:de\s+|du\s+)?visa\s*[:.]?\s*|visa\s+n[°ºo.]*\s*"
    # Togo : « SP.TG 5223 » est le numéro d'AMM lui-même.
    r"|(?=sp\.?\s?tg\s?\d)",
    "en": r"marketing\s+authori[sz]ation\s+(?:no|n[°º])\.?\s*",
    "decision": r"decision\s+n\s*[°º'’*]?\s*|(?:^|\n)\s*n\s*[°º'’*]\s*(?=\d)",
}


def _number_readings(plain: str, text: str) -> dict[str, list[str]]:
    readings: dict[str, list[str]] = {}
    for source, labels in _NUMBER_SOURCES.items():
        for match in re.finditer(rf"(?:{labels}){_NUMBER_TOKEN}", plain):
            value = text[match.start(1) : match.end(1)].rstrip("/_.-")
            # Lettres lues à la place de chiffres (« NS61501 ») dans un numéro purement numérique.
            if re.fullmatch(r"[0-9sSoO]+", value) and sum(c.isdigit() for c in value) >= 5:
                value = value.upper().replace("S", "5").replace("O", "0")
            if sum(character.isdigit() for character in value) < 4:
                continue
            kind = source
            # « N°11381207 /AMM/MINSANTE » : la ligne d'en-tête porte bien un numéro d'AMM.
            if source == "decision" and re.match(r"\s*[-—–]?\s*/?\s*amm\b", plain[match.end(1) :]):
                kind = "decision_amm"
            readings.setdefault(kind, []).append(value.upper()[:100])
    return readings


def _authorization_number(
    plain: str, text: str, labeled: str = "", decision_is_amm: bool = False
) -> tuple[str, list[str]]:
    """Numéro d'AMM confronté entre ses mentions ; une égalité entre lectures proches reste vide.

    `labeled` est la valeur d'un champ « Numéro AMM : … » en début de ligne, prioritaire.
    Renvoie le numéro retenu et les autres lectures du même numéro, à signaler.
    """
    readings = _number_readings(plain, text)
    if labeled:
        readings["label"] = [labeled]
    sources: dict[str, set[str]] = {}
    for source, values in readings.items():
        for value in values:
            sources.setdefault(normalize(value).replace(" ", ""), set()).add(source)
    originals = {
        normalize(value).replace(" ", ""): value for values in readings.values() for value in values
    }
    # Regroupe les lectures d'un même numéro (au plus deux caractères d'écart).
    clusters: list[list[str]] = []
    for key in sorted(sources, key=lambda item: (-len(sources[item]), item)):
        for cluster in clusters:
            if any(_edit_distance(key, other) <= 2 for other in cluster):
                cluster.append(key)
                break
        else:
            clusters.append([key])
    priority = ("label", "granted", "registration", "fr", "en", "decision_amm", "decision")

    def rank(cluster):
        best = min(priority.index(source) for key in cluster for source in sources[key])
        return (best, -max(len(sources[key]) for key in cluster))

    for cluster in sorted(clusters, key=rank):
        # Un numéro d'acte (« Décision N° … ») sans autre mention n'est pas un numéro d'AMM.
        # Sauf là où la décision d'homologation porte elle-même le numéro (Congo : « DECISION N°
        # CV/04C-07G/09 … visa d'homologation »), et seulement faute de toute autre mention.
        if all(sources[key] == {"decision"} for key in cluster):
            if decision_is_amm and len(clusters) == 1:
                return originals[cluster[0]], []
            continue
        support = sorted(cluster, key=lambda key: -len(sources[key]))
        if len(support) > 1 and len(sources[support[0]]) == len(sources[support[1]]):
            return "", [originals[key] for key in support]
        return originals[support[0]], [originals[key] for key in support[1:]]
    return "", []


_HOLDER_FORMS = (
    r"(?:pv[ti1]\.?\s*l[ti1]d\.?|private\s+limited|ltd\.?|limited|s\.?a\.?r\.?l\.?|s\.?a\.?s\.?"
    r"|inc\.?|gmbh|plc|s\.?a\.)"
)
# Début d'adresse : le nom du titulaire s'arrête avant.
_ADDRESS_WORDS = re.compile(
    r"^(?:city|square|village|office|street|road|house|avenue|rue|bp|boulevard|zone|plot|bloc)\b",
    re.I,
)


def _granted_holder(text: str) -> str:
    """Titulaire nommé après « accordée à » / « granted to » (ligne en capitales qui suit)."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.search(
            r"accord[ée]e?\s+[aà4]\b|granted\s+(?:to|so)\b|renewed\s+to\b", line, re.I
        ):
            continue
        for candidate in lines[index + 1 : index + 6]:
            if re.search(r"pharmaceutical|pharmaceutique|en vue du|for sale", candidate, re.I):
                break
            if re.search(r"\b(?:LOI|LAW|ARTICLE|AUTHORI[SZ]ATION|AUTORISATION)\b", candidate, re.I):
                continue
            name = []
            for token in candidate.split():
                if (
                    any(character.isdigit() for character in token)
                    or token.startswith("(")
                    or _ADDRESS_WORDS.match(token)
                ):
                    break
                name.append(token)
                if token.endswith(","):
                    break
            holder = " ".join(name).strip(" ,.;:_-/")
            form = re.search(rf"^.*?\b{_HOLDER_FORMS}(?=\s|$)", holder, re.I)
            if form:
                holder = form.group(0)
            # Confusions d'OCR courantes dans la forme juridique (« PVI LID » pour « PVT LTD »).
            holder = re.sub(r"\bPV[I1]\b", "PVT", re.sub(r"\bL[I1]D\b", "LTD", holder))
            holder = re.sub(r"(?:\s*[._])+$", "", re.sub(r"\s*\.\s*\.+", "", holder)).strip()
            letters = [character for character in holder if character.isalpha()]
            if (
                len(holder.split()) >= 2
                and len(letters) >= 8
                and sum(character.isupper() for character in letters) >= 0.8 * len(letters)
            ):
                return holder[:255]
    return ""


def _product_line(text: str) -> str:
    """Dénomination imprimée sur sa propre ligne après « the following pharmaceutical product »."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        folded = fold(line)
        if not re.search(
            r"(?:sale|distribution|following)[^\n]{0,60}pharmaceutical\s+product\b(?!s)"
            r"|(?:debit|onereux)[^\n]{0,60}specialite\s+pharmaceutique",
            folded,
        ):
            continue
        for candidate in lines[index + 1 : index + 5]:
            cleaned = re.sub(r"^[^A-Za-z0-9]+|[®™*]+", "", candidate).strip(" .;:")
            folded_candidate = fold(cleaned)
            if re.search(r"pharmaceutical product|for sale|free distribution", folded_candidate):
                continue
            if re.match(r"(?:dci|inn|dosage|presentation|prix|price|site)\b", folded_candidate):
                break
            if sum(character.isalpha() for character in cleaned) >= 3:
                return cleaned[:120]
    return ""


# Décisions groupées : un tableau « Dénomination | N° AMM | Date » pour des dizaines de produits.
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
    return rows if len(rows) >= 3 else []


def _mentions(text: str, names) -> list:
    padded = f" {normalize(text)} "
    matches = []
    for obj, labels in names:
        hits = [normalize(label) for label in labels if normalize(label)]
        hits = [label for label in hits if f" {label} " in padded]
        if hits:
            matches.append((obj, max(hits, key=len)))
    # A presentation's complete name beats its generic-name prefix.
    return [
        obj
        for obj, hit in matches
        if not any(hit != longer and f" {hit} " in f" {longer} " for _, longer in matches)
    ]


def recognize_file(upload, countries, products, root_name: str = "") -> dict:
    extraction = upload.extraction or {}
    text = extraction.get("text", "")[:160_000]
    plain = fold(text)
    path = upload.relative_path
    # « : » dans un chemin macOS est un « / » du Finder (« 50MG:5ML » = « 50MG/5ML »).
    path_text = normalize(f"{root_name} {path}".replace(":", "/"))
    basename = normalize(PurePosixPath(path).name)
    header = normalize(text[:1200])
    reliability = min(98, int(extraction.get("confidence", 0)))
    if extraction.get("source") == "ocr":
        reliability = min(reliability, 80)

    # A leaflet can quote an authorization number without being the decision that proves it.
    ancillary = bool(re.search(r"\b(rcp|notice|leaflet|resume des caracteristiques)\b", basename))
    ancillary = ancillary or bool(re.match(r"(?:resume des caracteristiques|notice\b)", header))
    receipt = bool(
        re.search(r"\b(recepisse|accuse de reception|receipt)\b", header + " " + basename)
    )
    letter = bool(re.search(r"\b(courrier|lettre|letter)\b", basename))
    # Autorisation temporaire d'importation (Mauritanie) : document annexe, jamais une AMM.
    temporary = bool(
        re.search(r"autorisation temporaire d importation", header) or re.match(r"ati\b", basename)
    )
    decision = bool(
        re.search(
            r"\b(decision|arrete|autorisation de mise sur le marche|marketing authori[sz]ation"
            r"|visa (?:de commercialisation|d homologation|d enregistrement)|homologation"
            r"|approval for the registration|numero amm)\b",
            header,
        )
        # Décisions dont l'en-tête est illisible mais qui portent « Numéro AMM : … ».
        or re.search(r"(?:^|\n)\s*numero\s+(?:d['’ ]?)?amm\s*:", plain)
        # Titres de scans aux espaces perdus (« MISE SUR LEMARCHE ») ou en anglais seul.
        or re.search(
            r"autorisationdemisesurlemarche|authori[sz]ationtomarket|marketingauthori[sz]ation",
            header.replace(" ", ""),
        )
    )
    official = (
        decision
        and not ancillary
        and not receipt
        and not letter
        and not temporary
        and reliability >= 65
    )
    # Une ATI est rangée comme pièce annexe (« Autre ») : elle ne prouve pas l'AMM.
    kind = "RECEPISSE" if receipt else "COURRIER" if letter else "AMM" if official else "AUTRE"

    product_names = [
        (product, [product.name, *[a.raw_name for a in product.aliases.all()]])
        for product in products
    ]
    explicit_product = _label_value(
        plain,
        r"(?:nom\s+(?:du\s+)?(?:produit|medicament)|produit|specialite(?:\s+pharmaceutique)?"
        r"|denomination(?:\s+(?:du\s+)?(?:medicament|produit))?|product(?:\s+name)?)",
        text,
    )
    # Décision bilingue : la dénomination occupe sa propre ligne après « pharmaceutical product ».
    product_line = "" if explicit_product else _product_line(text)
    explicit_product = explicit_product or product_line
    matched_text = _mentions(explicit_product or text, product_names)
    matched_path = _mentions(path_text, product_names)
    # Décision groupée (tableau, ou liste de plusieurs produits du catalogue) : elle ne désigne
    # pas un produit à elle seule ; la ligne du produit du dossier est choisie plus tard.
    rows = table_rows(text)
    grouped = bool(rows) or (not explicit_product and len(matched_text) >= 3)
    if grouped:
        matched_text = []
    matched_products = matched_text or matched_path
    product_confidence = reliability if matched_text else 60 if matched_path else reliability

    explicit_country = _label_value(plain, r"pays|country", text)
    country_names = [(country, [country.name, country.iso2]) for country in countries]
    country_text = _mentions(explicit_country, country_names) if explicit_country else []
    if not country_text:
        # The first lines describe the issuing authority; a manufacturer's address does not.
        authority_lines = "\n".join(
            line
            for line in plain.splitlines()[:14]
            if re.search(r"republique|republic|ministere|pays|country", line)
        )
        country_text = _mentions(authority_lines, country_names)
    country_path = _mentions(path_text, country_names)
    matched_countries = country_text or country_path
    country_confidence = reliability if country_text else 65 if country_path else 0

    labeled_number = _label_value(
        plain,
        r"(?:numero|n[°ºo.]*)\s*(?:d['’ ]*)?(?:amm|autorisation(?: de mise sur le marche)?)"
        r"|(?:amm|autorisation de mise sur le marche)\s*(?:n[°ºo.]*|numero)?"
        r"|(?:numero|n[°ºo.]*)\s*(?:du\s+)?renouvellement",
        text,
    )
    # Coupe « 00152 du 28/04/2025 » : recherche sur la forme repliée, découpe sur l'original.
    # Certificat guinéen : « PGHT N° E-AMM Début de validité Fin de validité » puis, ligne
    # suivante, « 22 EURO 5264 21/05/2024 21/05/2029 ».
    certificate = re.search(
        r"n\S{0,2}\s*e?\W?amm[^\n]*debut\s+de\s+validite[^\n]*\n[^\n]*?(?<![\d,.])(\d{4,6})\s+"
        r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})",
        plain,
    )
    if certificate and not labeled_number:
        labeled_number = certificate.group(1)
    cut = re.search(r"\s+(?:du|date|delivre|valable|pour)\b", fold(labeled_number))
    if cut:
        labeled_number = labeled_number[: cut.start()]
    decision_is_amm = bool(re.search(r"visa d.?homologation|portant homologation", plain))
    number, number_variants = _authorization_number(
        plain, text, labeled_number.upper()[:100], decision_is_amm
    )
    holder = (
        _label_value(
            plain,
            r"titulaire(?:\s+de\s+l['’ ]?amm)?|laboratoire|holder"
            r"|marketing authori[sz]ation holder",
            text,
        )
        or _granted_holder(text)
    )[:255]
    start_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?(?:debut|delivrance|de\s+delivrance|prise d['’ ]effet)"
        r"|delivree?\s+le|debut\s+de\s+validite|valable\s+(?:a compter du|du)"
        r"|date\s+d['’ ]effet|start\s+date|registration\s+date|date\s+of\s+registration"
        r"|date\s+d['’ ]enregistrement|date\s+du\s+visa",
    )
    decision_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?(?:decision|signature)|decision\s+du|fait\s+a\s+[^\n,]{1,50},?\s+le",
    )
    end_date = _labeled_date(
        plain,
        r"date\s+(?:de\s+)?fin|date\s+d['’ ]expiration|expire\s+le|valable\s+jusqu['’ ]au"
        r"|fin\s+de\s+validite|end\s+date|expiration\s+date|expiry\s+date",
    )
    # « Numéro AMM : 0003/CN/06/2019 du 09 Déc. 2019 au 08 Déc. 2024 »
    # « … renouvelée pour une durée de cinq (5) ans allant du 27 avril 2025 au 27 avril 2030 »
    period_range = re.search(
        rf"(?:amm|visa|numero|n[°º]|allant|valable|validite)[^\n]{{0,60}}?\bdu\s+"
        rf"({DATE_PATTERN})\s+au\s+({DATE_PATTERN})",
        plain,
    )
    if certificate and not start_date:
        start_date = parse_date(certificate.group(2))
        end_date = end_date or parse_date(certificate.group(3))
    if period_range and not start_date:
        start_date = parse_date(period_range.group(1))
        end_date = end_date or parse_date(period_range.group(2))
    if not decision_date:
        # Lieu et date de signature en tête ou en pied (« COTONOU, le 16 AVR 2019 »,
        # « Bamako, le 24 SEP 2020 », « Djibouti le 27/02/2024 »).
        signed = re.search(
            rf"(?:^|\n)[^\n]{{0,60}}?\b(?:{_SIGNATURE_PLACES}|fait\s+a\s+[a-z' -]{{3,25}})"
            rf"\s*,?\s*(?:le|lc|te)\s*[.:,]?\s*({DATE_PATTERN})",
            plain,
        )
        decision_date = parse_date(signed.group(1)) if signed else None
    if not decision_date:
        # Niger : la décision reprend la date de l'avis de la commission d'homologation.
        opinion = re.search(
            rf"(?:commission\s+nationale\s+d.?homologation|\bcnh\w*)[^\n]{{0,120}}?en\s+date\s+du\s*({DATE_PATTERN})",
            plain,
        )
        decision_date = parse_date(opinion.group(1)) if opinion else None
    if not end_date and start_date:
        interval = re.search(rf"valable\s+du\s+{DATE_PATTERN}\s+au\s+({DATE_PATTERN})", plain)
        end_date = parse_date(interval.group(1)) if interval else None
    if not start_date:
        # « La validité de cette autorisation est limitée à cinq (5) ans à partir du … »
        validity_start, validity_end = _validity_period(plain)
        if validity_start:
            start_date = validity_start
            end_date = end_date if end_date and end_date > start_date else validity_end

    # The nearest renewal directory is stable across files and retains multiple periods.
    renewal_parts = [
        normalize(part)
        for part in PurePosixPath(path).parts[:-1]
        if re.search(r"\b(renouvellement|renouv|renewal)\b", normalize(part))
    ]
    # « La demande de renouvellement de l'AMM doit être déposée… » figure aussi dans une AMM
    # d'origine : cette clause ne fait pas d'une décision un renouvellement.
    renewal_header = re.sub(
        r"demande de renouvellement|application for (?:the )?renewal", " ", header
    )
    renewal_content = bool(re.search(r"\b(renouvellement|renewal)\b", renewal_header)) or bool(
        re.search(
            r"renouvellement de l['’ ]?autorisation|renewal of the authori[sz]ation"
            r"|\best[ -]renouvelee\b|\bis hereby renewed\b",
            plain,
        )
    )
    renewal_filename = bool(re.search(r"\b(renouvellement|renouv|renewal)\b", basename))
    is_renewal = bool(renewal_parts or renewal_content or renewal_filename)
    period = "original"
    uncertain_period = False
    if is_renewal:
        if renewal_parts:
            period = "renewal-" + renewal_parts[-1].replace(" ", "-")
        elif start_date or decision_date:
            period = "renewal-" + (start_date or decision_date)
        elif number and official:
            period = "renewal-" + normalize(number).replace(" ", "-")
        else:
            period = "renewal-unresolved"
            uncertain_period = True
    original_folder = any(
        re.search(r"\b(origine|original|initiale?)\b", normalize(part))
        for part in PurePosixPath(path).parts[:-1]
    )
    if original_folder and is_renewal and official:
        uncertain_period = True

    return {
        "file_id": str(upload.pk),
        "path": path,
        "kind": kind,
        "official": official,
        "period": period,
        "uncertain_period": uncertain_period,
        "confidence": reliability,
        "product_ids": [str(product.pk) for product in matched_products],
        "product_name": matched_products[0].name
        if len(matched_products) == 1
        else explicit_product,
        "explicit_product_name": explicit_product,
        # Libellé « Produit : … » ou simple ligne de dénomination (insuffisante pour créer).
        "explicit_product_labeled": bool(explicit_product) and not product_line,
        "product_source": "text" if matched_text else "path" if matched_path else "",
        "product_confidence": product_confidence,
        "grouped": grouped,
        "temporary_import": temporary,
        "table_rows": rows,
        "country_ids": [str(country.pk) for country in matched_countries],
        "country_confidence": country_confidence,
        # Le numéro d'une décision groupée est celui de la ligne du produit, pas celui de l'acte.
        "number": number if official and not grouped else "",
        "number_variants": number_variants if official and not grouped else [],
        "holder": holder if official else "",
        "start_date": start_date if official else None,
        "decision_date": decision_date if official else None,
        "end_date": end_date if official else None,
        # Un récépissé porte la date de dépôt (« Déposé le 01/03/2026 »), pas une date « Date : ».
        "document_date": decision_date
        or start_date
        or _labeled_date(plain, r"date|deposee?\s+le|recu\s+le|received\s+on"),
    }
