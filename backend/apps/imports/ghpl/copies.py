"""Fiches en double dans un même pays : la même présentation suivie sous deux libellés.

Jusqu'à la 1.1.2, l'import du registre cherchait d'abord le libellé exact dans tout le catalogue.
Une présentation « Classement seul » d'un pays (« SALBUTUS 2MG-5ML SIROP-SUSP BUV 100ML » en
Côte d'Ivoire) pouvait ainsi être rattachée au produit d'un autre pays (« SALBUTUS 2MG/5ML SOL
BUV FL/100ML », libellé du Sénégal) : une seconde fiche s'ouvrait à côté de celle du pays, sans
scan, avec les mêmes dates, et parfois le même dépôt en double (deux rappels).

Une fiche est repérée quand :
- aucun libellé du registre de son pays ne la désigne (son nom vient d'un autre pays) ;
- une seule fiche du pays, désignée par le registre, est la même présentation (marque, forme,
  dosages, boîte).

Elle est une *copie* quand elle n'apporte rien : aucun document, aucun dossier de dépôt ni
import de dossier, des dates et un n° d'origine identiques (ou vides), et chacun de ses
renouvellements se retrouve sur l'autre fiche. Seule une copie peut être fusionnée, et
seulement à la demande d'une personne (« Fusionner » dans Imports Excel) : rien n'est perdu.
Les autres sont listées « à vérifier » avec la différence trouvée.
"""

from __future__ import annotations

from collections import defaultdict

from django.db import transaction

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.normalize import product_key

from ..registry import COUNTRIES, _plain, same_presentation

LISTED = 200
REASON = "Fiche en double fusionnée"
REASON_MAX = 100  # longueur du motif dans l'historique (django-simple-history)


def _labels_by_country(records: list[dict]) -> dict[str, set[str]]:
    """Clés des libellés du registre, par pays (ISO2)."""
    labels: dict[str, set[str]] = defaultdict(set)
    for record in records:
        iso2 = COUNTRIES.get(_plain(record.get("Pays")))
        if not iso2:
            continue
        for column in ("Presentation", "Referentiel"):
            key = product_key(record.get(column))
            if key:
                labels[iso2].add(key)
    return labels


def _number(value: str) -> str:
    from ..scans import number_key

    return number_key(value or "")


def _same_renewal(renewal: Renewal, others: list[Renewal]) -> bool:
    return any(
        other.workflow_status == renewal.workflow_status
        and other.start_date == renewal.start_date
        and other.end_date == renewal.end_date
        and other.filing_date == renewal.filing_date
        and (not renewal.number or _number(other.number) == _number(renewal.number))
        for other in others
    )


def copy_problem(copy: MarketingAuthorization, keep: MarketingAuthorization) -> str | None:
    """Ce que la fiche `copy` apporte de plus que `keep` (None : c'est une simple copie)."""
    if copy.documents.exists():
        return "elle a des documents"
    if copy.original_number and _number(copy.original_number) != _number(keep.original_number):
        return f"n° d'origine différent ({copy.original_number} / {keep.original_number or '—'})"
    if copy.original_start_date and copy.original_start_date != keep.original_start_date:
        return "date d'origine différente"
    if copy.original_end_date_manual and copy.original_end_date != keep.original_end_date:
        return "fin de validité d'origine différente"
    if copy.dossier_imports.exists() or copy.documentary_changes.exists():
        return "elle a servi dans un import de dossier"
    if hasattr(copy, "binder_check"):
        return "elle a été vérifiée dans les classeurs"
    kept = list(keep.renewals.all())
    for renewal in copy.renewals.all():
        if hasattr(renewal, "deposit"):
            return f"renouvellement {renewal.sequence} : dossier de dépôt"
        if not _same_renewal(renewal, kept):
            return f"renouvellement {renewal.sequence} absent de l'autre fiche"
    return None


def _entry(copy: MarketingAuthorization, keep: MarketingAuthorization) -> dict:
    problem = copy_problem(copy, keep)
    return {
        "country": copy.country.iso2,
        "copy": str(copy.pk),
        "copy_name": copy.product.name,
        "keep": str(keep.pk),
        "keep_name": keep.product.name,
        "mergeable": problem is None,
        "reason": problem or "",
    }


def find_copies(records: list[dict]) -> list[dict]:
    """Fiches en double d'après le registre complet (`_Consolidation`)."""
    labels = _labels_by_country(records)
    by_country: dict[str, list[MarketingAuthorization]] = defaultdict(list)
    queryset = MarketingAuthorization.objects.select_related("product", "country").filter(
        country__iso2__in=list(labels)
    )
    for amm in queryset:
        by_country[amm.country.iso2].append(amm)
    found = []
    for iso2, amms in sorted(by_country.items()):
        known = labels[iso2]
        tracked = [amm for amm in amms if amm.product.key in known]
        for amm in amms:
            if amm.product.key in known:
                continue
            same = [
                other
                for other in tracked
                if same_presentation(amm.product.name, other.product.name)
            ]
            if len(same) == 1:
                found.append(_entry(amm, same[0]))
    found.sort(key=lambda e: (not e["mergeable"], e["country"], e["copy_name"]))
    return found[:LISTED]


def merge_copy(copy_id: str, keep_id: str, user=None) -> str | None:
    """Fusionne la copie dans la fiche gardée ; renvoie le motif d'un refus."""
    from ..models import GhplSyncedFile, ImportRow

    with transaction.atomic():
        pair = {
            str(amm.pk): amm
            for amm in MarketingAuthorization.objects.select_for_update()
            .select_related("product", "country")
            .filter(pk__in=[copy_id, keep_id])
        }
        copy, keep = pair.get(str(copy_id)), pair.get(str(keep_id))
        if copy is None or keep is None or copy.pk == keep.pk:
            return "fiche introuvable (déjà fusionnée ?)"
        if copy.country_id != keep.country_id:
            return "les deux fiches ne sont pas du même pays"
        if not same_presentation(copy.product.name, keep.product.name):
            return "ce ne sont pas les mêmes présentations"
        problem = copy_problem(copy, keep)
        if problem:
            return f"à vérifier : {problem}"
        ImportRow.objects.filter(amm=copy).update(amm=keep)
        GhplSyncedFile.objects.filter(amm=copy).update(amm=keep)
        copy._change_reason = f"{REASON} dans « {keep.product.name} »"[:REASON_MAX]
        if user is not None:
            copy._history_user = user
        copy.delete()  # renouvellements identiques, alertes et rappels de la copie avec elle
        keep._change_reason = f"{REASON} : « {copy.product.name} »"[:REASON_MAX]
        keep.save()
    return None
