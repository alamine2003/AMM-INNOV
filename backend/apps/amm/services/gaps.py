"""Manques d'une fiche AMM, pour agir vite : le plan d'action et le filtre « manque » de la liste.

Chaque manque est une condition simple sur la fiche, sans comparer une AMM à une autre :

- `no_original` : origine non identifiée (n° ou date de début de l'AMM d'origine absents) ;
- `original_scan` : décision d'origine sans scan ;
- `missing_renewal` : sans renouvellement — l'AMM d'origine est échue et aucun renouvellement
  n'est enregistré (ni obtenu, ni en cours) ;
- `renewal_scan` : renouvellement obtenu sans scan de la décision ;
- `to_file` : renouvellement à déposer — AMM expirée ou à renouveler, sans renouvellement en
  cours, et dont l'historique est par ailleurs enregistré.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q

from apps.core.dates import today as reference_today

from ..models import MarketingAuthorization, Renewal

S = MarketingAuthorization.Status
W = Renewal.WorkflowStatus
# Renouvellements qui comptent : obtenu, ou en cours (planifié → en instruction).
LIVE = (W.OBTENU, W.PLANIFIE, W.EN_PREPARATION, W.DEPOSE, W.EN_INSTRUCTION)
IN_PROGRESS = (W.PLANIFIE, W.EN_PREPARATION, W.DEPOSE, W.EN_INSTRUCTION)

# Ordre d'affichage du plan d'action, avec le libellé et l'action proposée.
GAPS: dict[str, dict[str, str]] = {
    "no_original": {
        "label": "Origine non identifiée",
        "hint": "N° ou date de l'AMM d'origine absents : complétez-les depuis la décision.",
        "action": "Compléter l'origine",
    },
    "missing_renewal": {
        "label": "Sans renouvellement",
        "hint": "L'AMM d'origine est échue et aucun renouvellement n'est enregistré.",
        "action": "Ajouter le renouvellement",
    },
    "to_file": {
        "label": "Renouvellement à déposer",
        "hint": "Expirée ou à renouveler, sans renouvellement en cours.",
        "action": "Lancer le dépôt",
    },
    "original_scan": {
        "label": "Décision d'origine sans scan",
        "hint": "La fiche n'a pas le scan de la décision d'origine.",
        "action": "Ajouter le scan",
    },
    "renewal_scan": {
        "label": "Renouvellement sans scan",
        "hint": "Un renouvellement obtenu n'a pas le scan de sa décision.",
        "action": "Ajouter le scan",
    },
}


def _scan(**match):
    from apps.documents.models import Document

    return Document.objects.filter(
        kind=Document.Kind.AMM, is_current=True, archived_at__isnull=True, **match
    )


def gap_condition(gap: str) -> Q:
    """Condition (Q) d'un manque sur les AMM ; ValueError si le manque est inconnu."""
    today = reference_today()
    renewals = Renewal.objects.filter(amm=OuterRef("pk"))
    if gap == "no_original":
        return Q(original_number="") | Q(original_start_date__isnull=True)
    if gap == "original_scan":
        return ~Exists(_scan(amm=OuterRef("pk"), renewal__isnull=True))
    if gap == "missing_renewal":
        return Q(original_end_date__lt=today) & ~Exists(renewals.filter(workflow_status__in=LIVE))
    if gap == "renewal_scan":
        obtained = Renewal.objects.filter(amm=OuterRef("pk"), workflow_status=W.OBTENU)
        unscanned = obtained.annotate(scanned=Exists(_scan(renewal=OuterRef("pk")))).filter(
            scanned=False
        )
        return Exists(unscanned)
    if gap == "to_file":
        return (
            Q(status__in=[S.EXPIRE, S.A_RENOUVELER])
            & ~Exists(renewals.filter(workflow_status__in=IN_PROGRESS))
            & ~gap_condition("missing_renewal")
        )
    raise ValueError(gap)


def with_gaps(queryset, gaps: list[str]):
    """Les AMM qui ont au moins un des manques demandés."""
    condition = Q()
    for gap in gaps:
        condition |= gap_condition(gap)
    return queryset.filter(condition)
