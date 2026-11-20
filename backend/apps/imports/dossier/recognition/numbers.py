"""N° d'AMM d'une décision, avec la source de chaque lecture."""

import re

from .text import _edit_distance, normalize

_NUMBER_TOKEN = r"([0-9a-z][0-9a-z/_.-]{0,40}(?:[ ](?=[0-9])[0-9a-z/_.-]{1,20}){0,2})"
# Chaque famille de mention est une lecture indépendante du même numéro : « Registration number »,
# la mention « AMM N° » française, sa traduction « Marketing Authorization No. », et la ligne
# « Décision N° » (qui, selon les pays, porte le numéro d'AMM ou un numéro d'acte distinct).
_NUMBER_SOURCES = {
    # Mali : « Sous le N° 24 — 000829 du 25 juin 2024 suivant Décision ministérielle
    # N° 2024-0000675/MSDS-SG du 15 avril 2024 » : l'AMM est la décision ministérielle.
    "ministerial": r"decision\s+ministerielle\s+n\S{0,2}\s*",
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
            if source == "ministerial":
                value = re.split(r"/\s*[a-z]", value, maxsplit=1, flags=re.I)[0]
            if (
                source == "decision"
                and not re.search(r"[a-z]", value, re.I)
                and not re.search(r"\d{8}|\d{4}\W{0,2}\d{3,}", value)
            ):
                # « DECISION N° 2023 /MSDS », « 2015. 7 7 » : numéro manuscrit illisible.
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
    priority = (
        "label",
        "ministerial",
        "granted",
        "registration",
        "fr",
        "en",
        "decision_amm",
        "decision",
    )

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


# --- Congo : le numéro d'AMM est le « Code » de l'article 2 (règle de Mohamed, 19/11/2026) ----
#
# « DECISION N° 26-0466 /MSP/DGSSSa/DPM-26 PORTANT HOMOLOGATION DE : … » : numéro de l'acte.
# « Article 2 : Les références de l'autorisation de mise sur le marché sont :
#   Code : VC-PSM-GM /27.06.2 B/N°7 JMPHS16 » : numéro d'AMM (« RVC-… » pour un renouvellement).
# « Article 3 : Les dispositions de la décision N° 18.716/MSP/DGMPL/DPM-18 du 20 MARS 2018, dont
#   le code produit est VC-PSM-GM/03.01.4 B/N°1 LOPOEHS8 … » : AMM d'origine, rappelée.
_CONGO_CODE_VALUE = r"((?:r\s?)?vc\s?[-–—_]\s?psm[^\n]{3,60})"
_CONGO_CODE = re.compile(
    rf"(?:^|\n)[^\S\n]*(?:code[^\S\n]*)?[:;.]?[^\S\n]*\n?[^\S\n]*{_CONGO_CODE_VALUE}"
)
_CONGO_LABELED_CODE = re.compile(
    r"references\s+d[^\n]{0,80}?mise\s+sur\s+le\s+marche\s+sont\s*:?\s*"
    r"code[^\S\n]*[:;.]?[^\S\n]*\n?[^\S\n]*([^\n]{4,70})"
)
_CONGO_CITED = re.compile(rf"code\s+produit\s+est\s*:?\s*{_CONGO_CODE_VALUE}")
# Modèle de la Direction de la pharmacie et du médicament de Brazzaville.
_CONGO_MODEL = re.compile(r"date\s+butoir|/\s?dpm\s?-\s?\d\d\b|code\s+produit\s+est")


def _clean_congo_code(value: str) -> str:
    """« RVC -PSM- GM / 09.03.3 B/N° 9 JMPHS12 » → « RVC-PSM-GM/09.03.3 B/N°9 JMPHS12 ».

    Les fautes de lecture constatées sur le serveur le 19/11/2026 sont reprises : « N? 4 »,
    « N®° 1 », « N°L » pour « N°1 », « 02.245 » pour « 02.24.5 », « GM Y27.06.2 » pour
    « GM/27.06.2 », et la référence écrite « 02.24.5 - B/N°1 » ou « 27.06.2.B/N°1 ».
    """
    # « 24,02.1 » : un point lu comme une virgule ne termine pas la référence (essai du
    # 20/11/2026 : le Code s'arrêtait à « RVC-PSM-GM/24 »).
    value = re.sub(r"(?<=\d)\s?,\s?(?=\d)", ".", value.strip())
    value = re.split(r"\s*[,;]|\s+non\s+contraires", value, maxsplit=1, flags=re.I)[0]
    value = re.sub(r"(?i)(GM)\s*[Y|]\s*(?=\d\d\.)", r"\1/", value)
    value = re.sub(r"\s*([/_–—-])\s*", lambda match: "/" if match[1] == "/" else "-", value)
    value = re.sub(r"(?i)\bN\s*[°º'’*o?®]{0,3}\s*(?=\d)", "N°", value)
    value = re.sub(r"(?i)\bN[°º'’?®]{1,3}\s*[LI|](?![A-Z0-9])", "N°1", value)
    value = re.sub(r"\b(\d\d)\.(\d\d)(\d)\b", r"\1.\2.\3", value)
    value = re.sub(r"(?i)(\d\d\.\d\d\.\d)\s*[-.]?\s*B\s*/", r"\1 B/", value)
    value = re.sub(r"\s{2,}", " ", value).strip(" .:").upper()
    # Suffixe « …HS16 » : chiffres lus comme des lettres (« JMPHSI6 »).
    tail = re.search(r"HS([0-9ILO|]{1,2})$", value)
    if tail:
        digits = tail[1].translate(str.maketrans({"I": "1", "L": "1", "|": "1", "O": "0"}))
        value = value[: tail.start(1)] + digits
    return _congo_canonical(value)[:100]


# Sigles des signataires relevés sur les décisions (… JMPHS16, LOPHS10, LOPOEHS8, AAE HS 8).
_CONGO_SIGNATORIES = ("JMP", "LOP", "LOPOE", "AAE")
_CONGO_SHAPE = re.compile(
    r"^(?P<prefix>[^/]{4,16})/(?P<reference>\d{1,2}\.\d{2}\.\d) B/N°(?P<rank>\d{1,2})"
    r"\s?(?P<initials>[A-Z0-9\]\[|]{2,6}?)(?P<gap>\s?)HS(?P<gap2>\s?)(?P<year>\d{1,2})$"
)
_CONGO_COMPLETE = re.compile(
    r"^R?VC-PSM-GM/\d{1,2}\.\d{2}\.\d B/N°\d{1,2} [A-Z]{2,6} ?HS ?\d{1,2}$"
)


def _congo_canonical(value: str) -> str:
    """Remet les parties fixes d'un Code dont la référence a été lue en entier.

    Quand « /27.06.2 B/N°7 … HS16 » est lu, ce qui précède ne peut être que « VC-PSM-GM » ou
    « RVC-PSM-GM » : « VORSM-ÈM », « VE-PSA-GM » et « RVC-PSM-6M » (essai du 20/11/2026) sont
    redressés. Le sigle du signataire est rapproché des sigles connus quand une seule lettre
    en diffère (« TMPHS12 » pour « JMPHS12 »). Les chiffres, eux, ne sont jamais devinés.
    """
    match = _CONGO_SHAPE.match(value)
    if not match:
        return value
    letters = re.sub(r"[^A-Z0-9]", "", match["prefix"])
    prefix = "RVC-PSM-GM" if letters.startswith("R") or len(letters) >= 8 else "VC-PSM-GM"
    initials = match["initials"]
    if initials not in _CONGO_SIGNATORIES:
        near = [
            known
            for known in _CONGO_SIGNATORIES
            if len(known) == len(initials)
            and sum(a != b for a, b in zip(known, initials, strict=True)) == 1
        ]
        if len(near) == 1:
            initials = near[0]
    suffix = f"{initials}{match['gap']}HS{match['gap2']}{match['year']}"
    return f"{prefix}/{match['reference']} B/N°{match['rank']} {suffix}"


def congo_code_complete(value: str) -> bool:
    """Vrai pour un Code entier : préfixe, référence, rang et sigle (« … B/N°7 JMPHS16 »)."""
    return bool(_CONGO_COMPLETE.match(_clean_congo_code(value or "")))


def congo_model(plain: str) -> bool:
    return bool(_CONGO_MODEL.search(plain))


def congo_code(plain: str, text: str) -> str:
    """Code de l'article 2 d'une décision du Congo, ou vide s'il est illisible."""
    labeled = _CONGO_LABELED_CODE.search(plain)
    # Une référence porte des chiffres et des séparateurs : pas la ligne « Titulaire » qui suit
    # un Code illisible.
    if labeled and re.search(r"\d", labeled[1]) and re.search(r"[/-]", labeled[1]):
        return _clean_congo_code(text[labeled.start(1) : labeled.end(1)])
    for match in _CONGO_CODE.finditer(plain):
        # Pas le code de l'AMM d'origine rappelé à l'article 3.
        if "code produit" in plain[max(match.start(1) - 40, 0) : match.start(1)]:
            continue
        return _clean_congo_code(text[match.start(1) : match.end(1)])
    return ""


def congo_cited_code(plain: str, text: str) -> str:
    """Code de l'AMM d'origine rappelé par un renouvellement (« dont le code produit est … »)."""
    match = _CONGO_CITED.search(plain)
    return _clean_congo_code(text[match.start(1) : match.end(1)]) if match else ""
