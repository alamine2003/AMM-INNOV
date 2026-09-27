"""Ce que fait l'archiviste sur une page : constater, corriger, signaler.

Une correction lue sur le papier fait foi : elle remplace la valeur de la fiche (historique
conservé avec l'auteur), et les écarts ouverts de l'import sur ce champ sont refermés.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import ensure_country_in_scope
from apps.amm.models import MarketingAuthorization, Renewal
from apps.imports.dossier.application import _reconcile_after_commit, _save_with_actor
from apps.imports.models import DossierReviewPoint

from .layout import SLOT_FIELDS, Binder, ensure_in_binder, last_obtained
from .models import BinderCheck, BinderExtraPage

REASON = "Vérifié sur le classeur papier"


def _json(value):
    return value.isoformat() if isinstance(value, date) else value


def _apply(amm, corrections, user) -> list[dict]:
    """Écrit les valeurs lues sur le papier ; renvoie ce qui a réellement changé."""
    applied = []
    renewal = last_obtained(list(Renewal.objects.select_for_update().filter(amm=amm)))
    touched = set()
    for correction in corrections:
        slot, field, value = correction["slot"], correction["field"], correction["value"]
        if slot == "renewal":
            if renewal is None:
                if value in (None, ""):
                    continue
                # Renouvellement présent dans le classeur mais inconnu de l'application.
                renewal = Renewal(amm=amm, workflow_status=Renewal.WorkflowStatus.OBTENU)
            target = renewal
        else:
            target = amm
        attr = SLOT_FIELDS[slot][field]
        old = getattr(target, attr)
        # Le sérialiseur a déjà typé les dates (date ou None).
        new = (value or "").strip() if field == "number" else value
        if old == new:
            continue
        setattr(target, attr, new)
        if field == "end_date":
            setattr(target, f"{attr}_manual", new is not None)
        applied.append({"slot": slot, "field": field, "old": _json(old), "new": _json(new)})
        touched.add(slot)
    if "original" in touched:
        _save_with_actor(amm, user, REASON)
        _ensure_order(amm.original_start_date, amm.original_end_date, "AMM d'origine")
    if "renewal" in touched and renewal is not None:
        _save_with_actor(renewal, user, REASON)
        _ensure_order(renewal.start_date, renewal.end_date, "renouvellement")
        _save_with_actor(amm, user, REASON)
    return applied


def _ensure_order(start, end, where):
    if start and end and end < start:
        raise ValidationError(f"La date de fin ({where}) précéderait la date de début.")


def _close_mismatches(amm, user) -> None:
    """Le papier a été vu : les écarts relevés par l'import sur cette page sont tranchés."""
    renewal = last_obtained(list(amm.renewals.all()))
    for point in DossierReviewPoint.objects.select_for_update().filter(
        amm=amm, status=DossierReviewPoint.Status.OPEN, code="value_mismatch"
    ):
        if point.renewal_id is None:
            target = amm
        elif renewal is not None and point.renewal_id == renewal.pk:
            target = renewal
        else:
            continue
        if not point.field or not hasattr(target, point.field):
            continue
        current = _json(getattr(target, point.field))
        point.status = (
            DossierReviewPoint.Status.APPLIED
            if current == point.scan_value
            else DossierReviewPoint.Status.IGNORED
        )
        point.resolved_by = user
        point.resolved_at = timezone.now()
        point.save(update_fields=["status", "resolved_by", "resolved_at"])


def record_check(binder: Binder, amm_id, *, result: str, corrections, note: str, user):
    with transaction.atomic():
        amm = (
            MarketingAuthorization.objects.select_for_update(of=("self",))
            .select_related("country", "product__range")
            .get(pk=amm_id)
        )
        ensure_country_in_scope(user, amm.country)
        ensure_in_binder(binder, amm)
        absent = result == BinderCheck.Result.ABSENT
        if absent and corrections:
            raise ValidationError("Un dossier absent du classeur ne peut pas être corrigé.")
        applied = _apply(amm, corrections, user) if corrections else []
        check = BinderCheck.objects.filter(amm=amm).first() or BinderCheck(amm=amm)
        history = list(check.corrections or []) + applied
        check.corrections = history
        if absent:
            check.result = BinderCheck.Result.ABSENT
        else:
            check.result = BinderCheck.Result.CORRIGE if history else BinderCheck.Result.CONFORME
            _close_mismatches(amm, user)
        check.note = note
        check.checked_by = user
        check.checked_at = timezone.now()
        check._history_user = user
        check.save()
        if applied:
            transaction.on_commit(lambda: _reconcile_after_commit(amm.pk))
    return check


def undo_check(binder: Binder, amm_id, *, user) -> None:
    """Remet la page « à vérifier » ; les valeurs corrigées restent (voir l'historique)."""
    amm = MarketingAuthorization.objects.select_related("country", "product__range").get(pk=amm_id)
    ensure_country_in_scope(user, amm.country)
    ensure_in_binder(binder, amm)
    BinderCheck.objects.filter(amm=amm).delete()


def add_extra(binder: Binder, *, product_name: str, note: str, user) -> BinderExtraPage:
    ensure_country_in_scope(user, binder.country)
    return BinderExtraPage.objects.create(
        country=binder.country,
        binder_key=binder.key,
        product_name=" ".join(product_name.split()).upper(),
        note=note,
        created_by=user,
    )


def remove_extra(binder: Binder, extra_id, *, user) -> None:
    ensure_country_in_scope(user, binder.country)
    deleted, _ = BinderExtraPage.objects.filter(pk=extra_id, binder_key=binder.key).delete()
    if not deleted:
        raise ValidationError("Page en trop introuvable.")
