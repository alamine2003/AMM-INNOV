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

Une lecture n'est pas une certitude (1.3.8, essai du 20/11/2026 sur les pages 1 à 20) : une
période dont la proposition contredit ce qui est déjà saisi porte un `doubt`. Elle est
affichée pour être vue sur le papier et n'est jamais écrite sans demande explicite. Un Code
lu en partie seulement est montré, jamais proposé.
"""

import logging
import re
from datetime import date
from difflib import SequenceMatcher

from django.db import transaction

from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services.sequence import resequence
from apps.catalog.models import Country
from apps.documents.models import Document
from apps.imports.dossier.application import _reconcile_after_commit, _save_with_actor
from apps.imports.dossier.extraction import extract_file
from apps.imports.dossier.recognition.dates import (
    CONGO_VALIDITY_YEARS,
    congo_deadline_year,
    congo_period,
)
from apps.imports.dossier.recognition.numbers import (
    congo_code,
    congo_code_complete,
    congo_model,
)
from apps.imports.dossier.recognition.text import fold

from .layout import Binder, binder_amms
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


def _squash(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())  # « º » compte pour une lettre


def _same_number(left: str, right: str) -> bool:
    """« VC-PSM-GM /12.09.1 B/Nº3 » et « VC-PSM-GM/12.09.1.B/N°3 » sont le même numéro."""
    return _squash(left) == _squash(right)


def _completes(read: str, typed: str) -> bool:
    """Le numéro saisi est le Code lu, à des caractères manquants près (« VC-PSM-GM/N°9 … »)."""
    remaining = iter(_squash(read))
    return all(character in remaining for character in _squash(typed))


def _number_doubt(read: str, typed: str) -> str:
    """Pourquoi ne pas écrire le Code lu à la place du numéro saisi, ou vide."""
    if not typed or _completes(read, typed):
        return ""
    if congo_code_complete(typed):
        # Un Code entier déjà saisi vient d'une personne ou du registre : il prime sur l'OCR.
        return f"le Code lu « {read} » diffère du Code déjà saisi"
    if SequenceMatcher(None, _squash(read), _squash(typed)).ratio() >= 0.8:
        return f"le Code lu « {read} » diffère de peu du numéro saisi"
    return ""


def _iso(value):
    return value.isoformat() if value else None


def _february(value) -> str | None:
    """28 février de l'année d'une date connue."""
    return f"{value.year}-02-28" if value else None


def _read(document) -> tuple[str, str, str, str]:
    """(numéro lu, état de la lecture, texte replié, source du texte) d'une décision scannée."""
    extraction = extract_file(document)
    text = extraction.get("text") or ""
    plain = fold(text)
    source = extraction.get("source") or ""
    code = congo_code(plain, text)
    if code:
        return code, "code", plain, source
    if extraction.get("errors") or not text.strip():
        return "", "illisible", plain, source
    return "", "code-illisible" if congo_model(plain) else "ancien-modele", plain, source


def _period_proposal(target, slot: str, document) -> dict | None:
    names = FIELDS[slot]
    current = {field: getattr(target, attr) for field, attr in names.items()}
    number, reading, plain, source = (
        _read(document) if document is not None else ("", "sans-scan", "", "")
    )
    end_year = congo_deadline_year(plain)
    if end_year is not None:
        # « sera renouvelée en 2030 … date butoir du 28 février » : la décision fait foi.
        period = (f"{end_year - CONGO_VALIDITY_YEARS}-02-28", f"{end_year}-02-28")
    elif current["start_date"] or current["end_date"]:
        # Clause absente (ancien modèle, scan illisible, pas de scan) : les années connues sont
        # gardées, seul le jour passe au 28 février. Recalculer ici a donné des dates fausses
        # (essai du 19/11/2026 : une origine 2013 → 2017 proposée 2017 → 2021).
        period = (_february(current["start_date"]), _february(current["end_date"]))
    else:
        period = congo_period("", _iso(document.document_date) if document is not None else None)
        period = period or (None, None)
    changes = []
    doubts = []
    if number and not _same_number(number, current["number"]):
        if not congo_code_complete(number):
            reading = "code-partiel"  # montré, jamais écrit
        else:
            doubt = _number_doubt(number, current["number"])
            if doubt:
                doubts.append(doubt)
            changes.append({"field": "number", "old": current["number"], "new": number})
    for field, new in zip(("start_date", "end_date"), period, strict=True):
        if new and _iso(current[field]) != new:
            changes.append({"field": field, "old": _iso(current[field]), "new": new})
    if end_year is not None:
        known = [current["start_date"], current["end_date"]]
        moved = [
            value.year != int(new[:4]) for value, new in zip(known, period, strict=True) if value
        ]
        if moved and all(moved):
            # Une seule année fausse est une faute de saisie : la date butoir fait foi (page 5,
            # fin 2025 saisie pour 2024). Les deux années décalées, c'est une autre période :
            # la décision scannée n'est peut-être pas celle-ci (origine 2014 → 2018, scan de
            # la décision de 2018).
            doubts.append(
                f"la décision couvre {period[0][:4]} → {period[1][:4]}, pas les années enregistrées"
            )
    if not changes and reading not in ("code-illisible", "illisible", "code-partiel"):
        return None
    return {
        "slot": slot,
        "renewal": str(target.pk) if slot == "renewal" else None,
        "document": str(document.pk) if document is not None else None,
        "decision_date": _iso(document.document_date) if document is not None else None,
        "reading": reading,
        "read": number,
        "source": source,
        "doubt": " ; ".join(doubts) if changes else "",
        "changes": changes,
    }


def propose(*, pages: tuple[int, int] | None = None, progress=None) -> list[dict]:
    """Ce que la relecture changerait, page par page, dans l'ordre du classeur. N'écrit rien.

    `pages` : (première, dernière) page du classeur à relire, bornes comprises.
    """
    country = Country.objects.filter(iso2=COUNTRY).first()
    if country is None:
        return []
    amms = binder_amms(Binder(country=country))
    verified = set(
        BinderCheck.objects.filter(amm__country=country)
        .exclude(result=BinderCheck.Result.ABSENT)
        .values_list("amm_id", flat=True)
    )
    first, last = pages or (1, len(amms))
    proposals = []
    for index, amm in enumerate(amms, 1):
        if not first <= index <= last:
            continue
        decisions = sorted(
            (d for d in amm.current_documents if d.kind == Document.Kind.AMM),
            key=lambda d: (d.document_date, d.uploaded_at),
            reverse=True,
        )
        periods = []
        targets = [("original", amm, None)] + [
            ("renewal", renewal, renewal.pk)
            for renewal in sorted(amm.renewals.all(), key=lambda r: r.sequence)
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
                    "read": "",
                    "source": "",
                    "doubt": "",
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
            progress(index, amm.product.name, amm.pk in verified, periods)
    return proposals


def apply(
    proposals: list[dict],
    *,
    user=None,
    include_verified: bool = False,
    include_doubtful: bool = False,
) -> dict:
    """Écrit les propositions. Une valeur qui a changé depuis la relecture est laissée, une
    période douteuse aussi (sauf demande explicite)."""
    report = {
        "amms": 0,
        "fields": 0,
        "skipped_verified": 0,
        "skipped_doubtful": 0,
        "stale": 0,
        "errors": [],
    }
    for proposal in proposals:
        if proposal["verified"] and not include_verified:
            report["skipped_verified"] += 1
            continue
        try:
            with transaction.atomic():
                amm = MarketingAuthorization.objects.select_for_update().get(pk=proposal["amm"])
                written = 0
                for period in proposal["periods"]:
                    if period.get("doubt") and not include_doubtful:
                        report["skipped_doubtful"] += 1
                        continue
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
