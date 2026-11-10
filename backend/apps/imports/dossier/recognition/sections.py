"""Recueils découpés en décisions, et regroupement par spécialité."""

import re
from difflib import SequenceMatcher

from .text import fold, normalize

PAGE_BREAK = "\f"
# « … pour la spécialité : GENSET 10 mg comprimé », « l'autorisation … de la spécialité
# LITACOLD sirop … est renouvelée » : la dénomination suit sur la même ligne ou la suivante.
_SPECIALTY = re.compile(
    r"\b(?:la|votre)\s+specialite(?:\s+pharmaceutique)?\s*[:;]?\s{0,6}"
    r"(?=[^\n]*[a-z]{3})([^\n]{3,150})"
)


def decision_sections(text: str) -> list[dict]:
    """Découpe un recueil de décisions (une par spécialité) : dénomination et pages de chacune.

    Mali : « AMM groupée 23 DEC 2023 » réunit six décisions de deux pages, chacune « … pour la
    spécialité : GENFER® 100 mg/2 mL … » ; « Renouvellement AMM 15 PRODUITS 2019 » quinze
    décisions d'une page. Une section va de la page qui nomme la spécialité à la suivante.
    Sans séparateur de pages (lecture ancienne), les sections sont découpées dans le texte.
    """
    pages = text.split(PAGE_BREAK) if PAGE_BREAK in text else [text]
    offsets, position = [], 0
    for page in pages:
        offsets.append(position)
        position += len(page) + len(PAGE_BREAK)
    starts = []
    for number, page in enumerate(pages, 1):
        folded = fold(page)
        for match in _SPECIALTY.finditer(folded):
            label = page[match.start(1) : match.end(1)]
            # « « ESOMERAL 40mg B/30 comprimés » octroyée à … », « … B/10 doit être cédée … »
            label = re.split(
                r"»|\s(?:est|is|doit|octroy\w*|accord\w*|renouvel\w*|cede\w*|c[ée]d[ée]e)\s",
                label,
                maxsplit=1,
                flags=re.I,
            )[0].strip(" .;:,-«\"'")
            if sum(character.isalpha() for character in label) >= 3 and not re.match(
                r"(?:arrete|article|decide|vu|ci.dessus|repond|est|sont|dont|doit)\b", fold(label)
            ):
                starts.append((number, offsets[number - 1] + match.start(), label[:120]))
            if len(pages) > 1:
                break  # une décision par page au plus : la première mention la désigne
    sections = []
    # Un recueil réunit plusieurs actes complets, chacun avec son en-tête : sans en-têtes
    # répétés, les mentions multiples viennent d'une seule décision (« Analyse : … à la
    # spécialité » puis « … accordée à la spécialité : EXEMPLO »).
    folded = fold(text)
    headers = max(
        len(re.findall(r"republique\s+(?:du|de|d')", folded)),
        len(re.findall(r"(?:^|\n)[^\n]{0,40}\b(?:decision|arrete)\s+n\S{0,3}\s*\d", folded)),
    )
    if len(starts) > 1 and headers < 2:
        starts = starts[:1]
    for index, (page, start, label) in enumerate(starts):
        end_page = starts[index + 1][0] - 1 if index + 1 < len(starts) else len(pages)
        end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        if len(pages) > 1:
            # La décision commence en haut de sa page (en-tête, visas), pas à la dénomination.
            start = offsets[page - 1] if index else 0
            end = offsets[end_page] if end_page < len(pages) else len(text)
        sections.append(
            {
                "specialty": label,
                "first_page": page if len(pages) > 1 else None,
                "last_page": max(page, end_page) if len(pages) > 1 else None,
                "start": start,
                "end": end,
            }
        )
    return sections


def specialty_key(label: str) -> str:
    """Clé de comparaison d'une dénomination (« NORFLOZOLE (… ) 100 mg +100 mg » relu deux fois)."""
    return normalize(label)[:40]


def specialty_groups(sections: list[dict]) -> list[str]:
    """Dénominations distinctes d'un document : deux lectures voisines ne font qu'une."""
    groups: list[str] = []
    for section in sections:
        key = specialty_key(section["specialty"])
        if not any(
            key.startswith(other) or other.startswith(key)
            or SequenceMatcher(None, key[:25], other[:25]).ratio() >= 0.8
            for other in groups
        ):  # fmt: skip
            groups.append(key)
    return groups


