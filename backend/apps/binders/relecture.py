"""Relecture des décisions du Congo déjà rangées (1.3.6).

Jusqu'à la 1.3.5, l'application prenait le numéro de la décision (« 26-0466 ») pour le numéro
d'AMM et faisait courir la période de la date de signature. Au Congo, le numéro d'AMM est le
« Code » de l'article 2 et toute période va d'un 28 février à un 28 février, quatre ans plus
tard (règles de Mohamed, 19/11/2026). La ligne du Code, surlignée sur le papier, n'était pas
lue : chaque décision est donc relue (OCR compris) avec les règles actuelles.

Deux temps, pour qu'un humain valide avant toute écriture :

1. `propose()` relit et renvoie, fiche par fiche, ce qui changerait. Rien n'est modifié.
2. `apply()` écrit les propositions qu'on lui remet, une fiche par transaction, et laisse de
   côté toute valeur qui a changé entre-temps. Une page vérifiée sur le classeur papier n'est
   jamais touchée sans demande explicite.
"""

import logging
from datetime import date

from django.db import transaction

from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services.sequence import resequence
from apps.documents.models import Document
from apps.imports.dossier.application import _reconcile_after_commit, _save_with_actor
from apps.imports.dossier.extraction import extract_file
from apps.imports.dossier.recognition.dates import congo_period
from apps.imports.dossier.recognition.numbers import congo_code, congo_model
from apps.imports.dossier.recognition.text import fold

from .models import BinderCheck

logger = logging.getLogger(__name__)

COUNTRY = "CG"
REASON = "Relecture des décisions du Congo : Code de l'article 2, périodes au 28 février"
FIELDS = {
    "original": {
        "number": "original_number",
        "start_date": "original_start_date",
        "end_date": "original_end_date",
    },
    "renewal": {"number": "number", "start_date": "start_date", "end_date": "end_date"},
}


def _same_number(left: str, right: str) -> bool:
    """« VC-PSM-GM /12.09.1 B/Nº3 » et « VC-PSM-GM/12.09.1 B/N°3 » sont le même numéro."""

    def squash(value: str) -> str:
        return "".join((value or "").upper().replace("º", "°").split())

    return squash(left) == squash(right)


def _iso(value):
    return value.isoformat() if value else None


def _read(document) -> tuple[str, str, str]:
    """(numéro lu, état de la lecture, texte replié) pour la décision scannée d'une période."""
    extraction = extract_file(document)
    text = extraction.get("text") or ""
    plain = fold(text)
    code = congo_code(plain, text)
    if code:
        return code, "code", plain
    if extraction.get("errors") or not text.strip():
        return "", "illisible", plain
    return "", "code-illisible" if congo_model(plain) else "ancien-modele", plain


def _period_proposal(target, slot: str, document) -> dict | None:
    names = FIELDS[slot]
    current = {field: getattr(target, attr) for field, attr in names.items()}
    number, reading, plain = _read(document) if document is not None else ("", "sans-scan", "")
    # La clause « sera renouvelée en 2030 … date butoir » donne la période ; à défaut, l'année de
    # la décision ; sans scan, celle de la date de début déjà connue.
    dated = (document.document_date if document is not None else None) or current["start_date"]
    period = congo_period(plain, _iso(dated))
    changes = []
    if number and not _same_number(number, current["number"]):
        changes.append({"field": "number", "old": current["number"], "new": number})
    if period:
        for field, new in zip(("start_date", "end_date"), period, strict=True):
            if _iso(current[field]) != new:
                changes.append({"field": field, "old": _iso(current[field]), "new": new})
    if not changes and reading not in ("code-illisible", "illisible"):
        return None
    return {
        "slot": slot,
        "renewal": str(target.pk) if slot == "renewal" else None,
        "document": str(document.pk) if document is not None else None,
        "decision_date": _iso(document.document_date) if document is not None else None,
        "reading": reading,
        "changes": changes,
    }


def propose(*, limit: int | None = None, progress=None) -> list[dict]:
    """Ce que la relecture changerait, fiche par fiche, dans l'ordre du classeur. N'écrit rien."""
    amms = (
        MarketingAuthorization.objects.filter(country__iso2=COUNTRY)
        .select_related("product")
        .order_by("product__name")
    )
    verified = set(
        BinderCheck.objects.filter(amm__country__iso2=COUNTRY)
        .exclude(result=BinderCheck.Result.ABSENT)
        .values_list("amm_id", flat=True)
    )
    proposals = []
    for index, amm in enumerate(amms[:limit] if limit else amms, 1):
        decisions = list(
            Document.objects.current()
            .filter(amm=amm, kind=Document.Kind.AMM)
            .order_by("-document_date", "-uploaded_at")
        )
        periods = []
        targets = [("original", amm, None)] + [
            ("renewal", renewal, renewal.pk)
            for renewal in Renewal.objects.filter(amm=amm).order_by("sequence")
        ]
        for slot, target, renewal_id in targets:
            document = next((d for d in decisions if d.renewal_id == renewal_id), None)
            try:
                found = _period_proposal(target, slot, document)
            except Exception as exc:  # noqa: BLE001 — une décision illisible n'arrête pas la relecture
                logger.warning("Relecture impossible pour %s : %s", amm.product.name, exc)
                found = {
                    "slot": slot,
                    "renewal": str(renewal_id) if renewal_id else None,
                    "document": str(document.pk) if document is not None else None,
                    "decision_date": None,
                    "reading": "illisible",
                    "changes": [],
                }
            if found:
                periods.append(found)
        if periods:
            proposals.append(
                {
                    "page": index,
                    "amm": str(amm.pk),
                    "product": amm.product.name,
                    "verified": amm.pk in verified,
                    "periods": periods,
                }
            )
        if progress:
            progress(index, amm.product.name, periods)
    return proposals


def apply(proposals: list[dict], *, user=None, include_verified: bool = False) -> dict:
    """Écrit les propositions. Une valeur qui a changé depuis la relecture est laissée."""
    report = {"amms": 0, "fields": 0, "skipped_verified": 0, "stale": 0, "errors": []}
    for proposal in proposals:
        if proposal["verified"] and not include_verified:
            report["skipped_verified"] += 1
            continue
        try:
            with transaction.atomic():
                amm = MarketingAuthorization.objects.select_for_update().get(pk=proposal["amm"])
                written = 0
                for period in proposal["periods"]:
                    if period["slot"] == "renewal":
                        target = Renewal.objects.select_for_update().get(pk=period["renewal"])
                    else:
                        target = amm
                    names = FIELDS[period["slot"]]
                    touched = False
                    for change in period["changes"]:
                        attr = names[change["field"]]
                        current = getattr(target, attr)
                        current = _iso(current) if change["field"] != "number" else current
                        if (current or None) != (change["old"] or None):
                            report["stale"] += 1  # corrigée à la main depuis la relecture
                            continue
                        new = change["new"]
                        if change["field"] != "number":
                            new = date.fromisoformat(new)
                        setattr(target, attr, new)
                        if change["field"] == "end_date":
                            # Date imprimée sur la décision : elle ne se recalcule pas.
                            setattr(target, f"{attr}_manual", True)
                        touched = True
                        written += 1
                    if touched and target is not amm:
                        _save_with_actor(target, user, REASON)
                if written:
                    resequence(amm)
                    _save_with_actor(amm, user, REASON)
                    transaction.on_commit(lambda pk=amm.pk: _reconcile_after_commit(pk))
                    report["amms"] += 1
                    report["fields"] += written
        except Exception as exc:  # noqa: BLE001 — une fiche en erreur n'arrête pas les autres
            logger.exception("Relecture non appliquée pour %s", proposal["product"])
            report["errors"].append(f"{proposal['product']} : {exc}")
    return report
