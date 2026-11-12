"""Ordre d'urgence réglementaire, partout où l'on range ou propose d'agir.

Expirées d'abord, puis « à renouveler », puis valides, puis échéance inconnue ; à statut égal,
l'échéance la plus proche passe devant. Le rangement des dossiers et le plan d'action suivent
ce même ordre : le plus urgent est traité en premier.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Case, IntegerField, Value, When

from ..models import MarketingAuthorization

S = MarketingAuthorization.Status
STATUS_RANK = {S.EXPIRE: 0, S.A_RENOUVELER: 1, S.VALIDE: 2, S.INDETERMINE: 3}
UNKNOWN_RANK = 4


def urgency_key(status: str | None, end_date: date | None) -> tuple:
    """Clé de tri : plus petite = plus urgente."""
    return (STATUS_RANK.get(status, UNKNOWN_RANK), end_date or date.max)


def by_urgency(queryset):
    """Trie un queryset d'AMM par urgence réglementaire (même ordre que `urgency_key`)."""
    rank = Case(
        *[When(status=status, then=Value(value)) for status, value in STATUS_RANK.items()],
        default=Value(UNKNOWN_RANK),
        output_field=IntegerField(),
    )
    return queryset.annotate(urgency_rank=rank).order_by(
        "urgency_rank", "effective_end_date", "product__name"
    )


def amm_urgency(amm_ids) -> dict[str, tuple]:
    """Clé d'urgence de chaque AMM (identifiants en texte)."""
    rows = MarketingAuthorization.objects.filter(pk__in=list(amm_ids)).values_list(
        "pk", "status", "effective_end_date"
    )
    return {str(pk): urgency_key(status, end) for pk, status, end in rows}
