"""Texte des scans : sans accents ni casse, et distance d'édition."""

import re
import unicodedata


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
