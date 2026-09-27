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


def _product(name: str, range_code: str | None):
    """Le produit du catalogue (même libellé, alias ou même clé), créé s'il n'existe pas."""
    from apps.catalog.models import Product, ProductAlias, ProductRange
    from apps.catalog.normalize import normalize_product_name, product_key

    label = normalize_product_name(name)
    if not label:
        raise ValidationError("Indiquez le nom du produit tel qu'il figure sur le dossier.")
    range_obj = ProductRange.objects.filter(code=range_code).first() if range_code else None
    alias = ProductAlias.objects.filter(raw_name=label).select_related("product").first()
    product = (
        alias.product
        if alias
        else Product.objects.filter(name=label).first()
        or Product.objects.filter(key=product_key(label)).first()
    )
    if product is None:
        return Product.objects.create(name=label, range=range_obj), True
    if product.range_id is None and range_obj is not None:
        product.range = range_obj
        product.save(update_fields=["range"])
    return product, False


def add_page(
    binder: Binder,
    *,
    product_name: str,
    range_code: str | None,
    original_number: str,
    original_start_date,
    extra_id=None,
    user,
):
    """Page oubliée : l'AMM du produit dans ce pays est créée et prend sa place dans le
    classeur (ordre alphabétique). Une « page en trop » signalée peut ainsi devenir une page."""
    from .layout import binders_of

    ensure_country_in_scope(user, binder.country)
    if range_code is None and binder.part is not None:
        range_code = next((code for code in binder.part.ranges if code), None)
    with transaction.atomic():
        product, created = _product(product_name, range_code)
        existing = MarketingAuthorization.objects.filter(
            product=product, country=binder.country
        ).first()
        if existing is not None:
            raise ValidationError(
                f"{product.name} a déjà sa page dans les classeurs {binder.country.name}."
            )
        amm = MarketingAuthorization(
            product=product,
            country=binder.country,
            original_number=(original_number or "").strip(),
            original_start_date=original_start_date,
            notes="Page ajoutée depuis le classeur papier.",
        )
        amm._history_user = user
        amm._change_reason = "Page ajoutée depuis le classeur papier"
        amm.save()
        if extra_id:
            BinderExtraPage.objects.filter(pk=extra_id, binder_key=binder.key).delete()
    code = product.range.code if product.range_id else None
    landing = next(
        (b for b in binders_of(binder.country) if b.contains(code, product.name)), binder
    )
    return amm, landing, created


def import_page_scan(binder: Binder, amm_id, *, files: list, user):
    """« Importer le scan » depuis une page : le dossier est rangé sur cette AMM, lu comme un
    import de dossier (n° et dates relus, scan rangé, fiche corrigée si la décision le dit)."""
    from apps.imports.dossier.upload import stage_dossier
    from apps.imports.models import DossierImport

    amm = MarketingAuthorization.objects.select_related("country", "product__range").get(pk=amm_id)
    ensure_country_in_scope(user, amm.country)
    ensure_in_binder(binder, amm)
    if not files:
        raise ValidationError("Choisissez le scan de la décision (PDF ou image).")
    folder = f"{amm.country.name.upper()} - {amm.product.name}"
    batch = stage_dossier(
        uploads=files,
        paths=[f"{folder}/{getattr(file, 'name', 'scan.pdf')}" for file in files],
        root_name=folder,
        user=user,
    )
    # L'AMM est connue : l'analyse ne cherche pas le produit ni le pays, elle lit le scan.
    DossierImport.objects.filter(pk=batch.pk).update(amm=amm, country=amm.country)
    batch.refresh_from_db()
    return batch
