"""AMM supprimées : à la corbeille, elles ne reviennent pas par un import.

« Quand on supprime, on supprime » : une fiche AMM mise à la corbeille (depuis la liste, la fiche
ou le classeur) n'est recréée par aucun import (Excel, registre GHPL, scans classés, dossiers
pays). Elle revient seulement si quelqu'un la restaure depuis la corbeille.
"""

from __future__ import annotations

from apps.core.trash import trashed_values

from ..models import MarketingAuthorization

DELETED_REASON = (
    "AMM supprimée (à la corbeille) : l'import ne la recrée pas. Restaurez-la depuis la "
    "corbeille si elle existe bien."
)


def deleted_pairs() -> set[tuple[str, str]]:
    """Couples (produit, pays) des AMM à la corbeille, identifiants en texte."""
    return {
        (product, country)
        for product, country in trashed_values(MarketingAuthorization, "product", "country")
        if product and country
    }


def is_deleted(product, country, pairs: set[tuple[str, str]] | None = None) -> bool:
    """L'AMM de ce produit dans ce pays est à la corbeille (et n'existe pas ailleurs)."""
    if product is None or country is None or getattr(product, "pk", None) is None:
        return False
    pairs = deleted_pairs() if pairs is None else pairs
    return (str(product.pk), str(country.pk)) in pairs
