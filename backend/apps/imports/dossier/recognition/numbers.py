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


