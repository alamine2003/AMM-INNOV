"""Ce que sera l'AMM une fois le dossier rangé : échéance en vigueur, statut, état du dossier.

Calcul en mémoire, sans aucune écriture : on part de l'état actuel en base, on ajoute les
renouvellements que le dossier créerait, on applique les seules informations complétées
d'office (champs vides) — jamais les écarts avec une valeur enregistrée, qui deviennent des
points à vérifier plus tard — et on rattache les scans du dossier. Les règles
sont celles de `apps.amm.services.status.compute_amm_state` (source unique), si bien que la
projection et le bilan réel après validation coïncident.
"""

import copy
import logging
from datetime import date
from types import SimpleNamespace

from dateutil.relativedelta import relativedelta

from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services.status import compute_amm_state
from apps.documents.models import Document

logger = logging.getLogger(__name__)

AMM_FIELDS = ("original_number", "original_start_date", "original_end_date", "holder")
RENEWAL_FIELDS = ("number", "start_date", "end_date", "decision_date", "workflow_status")


def _typed(field, value):
    if field.endswith("date"):
        return date.fromisoformat(value) if value else None
    return value


def _iso(value):
    return value.isoformat() if value else None


def _fr(value):
    return value.strftime("%d/%m/%Y") if value else "?"


def missing_scan_label(renewals) -> str:
    """La décision en vigueur dont le scan manque (renouvellement obtenu le plus récent)."""
    obtained = [r for r in renewals if r.workflow_status == "OBTENU" and r.end_date]
    if obtained:
        last = max(obtained, key=lambda r: r.sequence)
        return (
            f"scan de la décision de renouvellement n° {last.number or '?'} "
            f"({_fr(last.start_date)})"
        )
    return "scan de la décision d'AMM d'origine"


def _derive_end(obj, start_field, end_field, validity_years):
    """Même règle que `save()` : l'échéance suit la date de début sauf saisie manuelle."""
    start = getattr(obj, start_field)
    if getattr(obj, end_field + "_manual"):
        return
    setattr(obj, end_field, start + relativedelta(years=validity_years) if start else None)


def build_projection(*, amm, product, country, original, renewals, changes, documents):
    if country is None:
        return None
    try:
        return _projection(amm, product, country, original, renewals, changes, documents)
    except Exception:  # noqa: BLE001 — la projection est indicative, jamais bloquante
        logger.exception("Projection de l'import de dossier impossible")
        return None


def _projection(amm, product, country, original, renewals, changes, documents):
    automatic = [change for change in changes if not change["requires_confirmation"]]
    if amm is not None:
        projected = copy.copy(amm)
        current = [copy.copy(r) for r in Renewal.objects.filter(amm_id=amm.pk)]
        scans = [
            SimpleNamespace(renewal_id=renewal_id)
            for renewal_id in Document.objects.filter(
                amm_id=amm.pk,
                kind=Document.Kind.AMM,
                is_current=True,
                archived_at__isnull=True,
            ).values_list("renewal_id", flat=True)
        ]
    else:
        projected = MarketingAuthorization(
            country=country, **({"product": product} if product else {})
        )
        for field in AMM_FIELDS:
            if original.get(field) not in (None, ""):
                setattr(projected, field, _typed(field, original[field]))
        projected.original_end_date_manual = bool(original.get("original_end_date"))
        _derive_end(projected, "original_start_date", "original_end_date", country.validity_years)
        current, scans = [], []

    by_pk = {str(r.pk): r for r in current}
    targets = {"amm": projected}
    for proposal in renewals:
        if proposal.get("existing_id"):
            targets[proposal["key"]] = by_pk.get(proposal["existing_id"])
    sequence = max((r.sequence for r in current), default=0)
    for proposal in sorted(renewals, key=lambda r: (r.get("start_date") or "", r["key"])):
        if proposal.get("existing_id"):
            continue
        sequence += 1
        renewal = Renewal(workflow_status=Renewal.WorkflowStatus.OBTENU, sequence=sequence)
        for field in ("number", "start_date", "end_date", "decision_date"):
            setattr(renewal, field, _typed(field, proposal.get(field)))
        renewal.end_date_manual = bool(proposal.get("end_date"))
        _derive_end(renewal, "start_date", "end_date", country.validity_years)
        current.append(renewal)
        targets[proposal["key"]] = renewal

    dirty = set()
    for change in automatic:
        obj = targets.get(change["target"])
        if obj is None:
            continue
        setattr(obj, change["field"], _typed(change["field"], change["new"]))
        if change["field"] in {"original_end_date", "end_date"}:
            setattr(obj, change["field"] + "_manual", True)
        dirty.add(change["target"])
    for key in dirty:
        if key == "amm":
            _derive_end(
                projected, "original_start_date", "original_end_date", country.validity_years
            )
        else:
            _derive_end(targets[key], "start_date", "end_date", country.validity_years)

    for proposal in documents:
        if proposal["kind"] != Document.Kind.AMM or proposal.get("duplicate_id"):
            continue
        target = targets.get(proposal["period"]) if proposal["period"] != "original" else None
        if proposal["period"] != "original" and target is None:
            continue
        scans.append(SimpleNamespace(renewal_id=target.pk if target else None))

    state = compute_amm_state(projected, renewals=current, documents=scans)
    obtained = [r for r in current if r.workflow_status == "OBTENU" and r.end_date]
    in_force = max(obtained, key=lambda r: r.sequence) if obtained else None
    keys = {str(obj.pk): key for key, obj in targets.items() if key != "amm" and obj is not None}
    timeline = [
        {
            "key": "original",
            "existing_id": None,
            "number": projected.original_number or "",
            "start_date": _iso(projected.original_start_date),
            "end_date": _iso(projected.original_end_date),
            "in_force": in_force is None,
        }
    ]
    for renewal in sorted(current, key=lambda r: (r.start_date or date.max, r.sequence)):
        key = keys.get(str(renewal.pk))
        if key is None and renewal.workflow_status != "OBTENU":
            continue  # renouvellement en cours hors dossier : pas une étape obtenue
        timeline.append(
            {
                "key": key,
                "existing_id": None if renewal._state.adding else str(renewal.pk),
                "number": renewal.number or "",
                "start_date": _iso(renewal.start_date),
                "end_date": _iso(renewal.end_date),
                "in_force": in_force is not None and renewal.pk == in_force.pk,
            }
        )
    return {
        "effective_end_date": _iso(state.effective_end_date),
        "ideal_filing_date": _iso(state.ideal_filing_date),
        "agency_filing_deadline": _iso(state.agency_filing_deadline),
        "status": state.status,
        "dossier_state": state.dossier_state,
        "missing_scan": (
            missing_scan_label(current) if state.dossier_state == "INCOMPLET" else None
        ),
        # Les écarts avec une valeur enregistrée ne sont pas comptés : ils restent des points à
        # vérifier, appliqués seulement sur action du réglementaire.
        "includes_corrections": False,
        "timeline": timeline,
    }
