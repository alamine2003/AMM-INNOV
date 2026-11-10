"""Titulaire de l'AMM et ligne du produit sur une décision."""

import re

from .text import fold

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
