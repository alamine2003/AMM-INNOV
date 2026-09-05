"""Applies a parsed workbook to the database, sheet by sheet (one transaction per sheet)."""

import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from apps.amm.models import MarketingAuthorization, Renewal
from apps.amm.services.status import compute_amm_state
from apps.catalog.models import Country, Product, ProductAlias, ProductRange
from apps.core.dates import override_today
from apps.core.dates import today as reference_today

from .excel_parser import ParsedRow, ParsedSheet, parse_workbook
from .models import ImportBatch, ImportRow

logger = logging.getLogger(__name__)

def _range_for(code: str | None, cache: dict) -> ProductRange | None:
    if code is None:
        return None
    if code not in cache:
        label = dict(ProductRange.Code.choices).get(code, code.title())
        cache[code], _ = ProductRange.objects.get_or_create(code=code, defaults={"label": label})
    return cache[code]


def _product_for(row: ParsedRow, range_obj: ProductRange | None) -> Product:
    alias = ProductAlias.objects.filter(raw_name=row.raw_name).select_related("product").first()
    if alias is not None:
        product = alias.product
    else:
        product = Product.objects.filter(name=row.product_name).first()
        if product is None:
            product = Product.objects.create(name=row.product_name, range=range_obj)
        ProductAlias.objects.get_or_create(product=product, raw_name=row.raw_name)
    if product.range_id is None and range_obj is not None:
        product.range = range_obj
        product.save(update_fields=["range"])
    return product


def _apply_renewal(amm: MarketingAuthorization, row: ParsedRow) -> bool:
    """Creates/updates the last renewal described by columns H/I/J. Returns True if changed."""
    if row.renewal_in_process:
        pending = (
            amm.renewals.filter(workflow_status__in=Renewal.PENDING_STATUSES)
            .order_by("-sequence")
            .first()
        )
        if pending is not None:
            if row.renewal_number and pending.number != row.renewal_number:
                pending.number = row.renewal_number
                pending._skip_signals = True
                pending.save()
                return True
            return False
        renewal = Renewal(
            amm=amm,
            workflow_status=Renewal.WorkflowStatus.DEPOSE,
            filing_date=None,  # the workbook does not hold the filing date
            number=row.renewal_number,
            notes="Importé depuis le classeur Excel (IN PROCESS).",
        )
        renewal._skip_signals = True
        renewal.save()
        return True

    if row.renewal_start_date is None:
        return False
    validity = relativedelta(years=amm.country.validity_years)
    computed_end = row.renewal_start_date + validity
    manual = row.renewal_end_date is not None and row.renewal_end_date != computed_end
    existing = (
        amm.renewals.filter(
            workflow_status=Renewal.WorkflowStatus.OBTENU, start_date=row.renewal_start_date
        )
        .order_by("-sequence")
        .first()
    )
    if existing is None:
        renewal = Renewal(
            amm=amm,
            workflow_status=Renewal.WorkflowStatus.OBTENU,
            number=row.renewal_number,
            start_date=row.renewal_start_date,
            end_date=row.renewal_end_date if manual else None,
            end_date_manual=manual,
            decision_date=row.renewal_start_date,
            notes="Importé depuis le classeur Excel.",
        )
        renewal._skip_signals = True
        renewal.save()
        return True
    changed = False
    if row.renewal_number and existing.number != row.renewal_number:
        existing.number = row.renewal_number
        changed = True
    if existing.end_date_manual != manual or (manual and existing.end_date != row.renewal_end_date):
        existing.end_date_manual = manual
        existing.end_date = row.renewal_end_date if manual else None
        changed = True
    if changed:
        existing._skip_signals = True
        existing.save()
    return changed


def _apply_row(
    row: ParsedRow, country: Country, range_cache: dict, today: date
) -> tuple[str, str, MarketingAuthorization]:
    range_obj = _range_for(row.range_code, range_cache)
    product = _product_for(row, range_obj)
    amm = (
        MarketingAuthorization.objects.select_related("country")
        .filter(product=product, country=country)
        .first()
    )
    created = amm is None
    if created:
        amm = MarketingAuthorization(product=product, country=country)
    changed = created
    validity = relativedelta(years=country.validity_years)

    if amm.original_number != row.original_number:
        amm.original_number = row.original_number
        changed = True
    if amm.original_start_date != row.original_start_date:
        amm.original_start_date = row.original_start_date
        changed = True
    computed_end = row.original_start_date + validity if row.original_start_date else None
    manual = row.original_end_date is not None and row.original_end_date != computed_end
    if manual:
        if not amm.original_end_date_manual or amm.original_end_date != row.original_end_date:
            amm.original_end_date_manual = True
            amm.original_end_date = row.original_end_date
            changed = True
        if computed_end is not None:
            row.warnings.append(
                f"date de fin Excel ({row.original_end_date:%d/%m/%Y}) différente "
                f"de la date calculée ({computed_end:%d/%m/%Y}) : valeur Excel conservée"
            )
    elif amm.original_end_date_manual:
        amm.original_end_date_manual = False
        changed = True
    if amm.dossier_state != row.dossier_state:
        amm.dossier_state = row.dossier_state
        changed = True

    if changed:
        amm._skip_signals = True
        amm.save()
    renewal_changed = _apply_renewal(amm, row)
    if renewal_changed or changed:
        amm._skip_signals = True
        amm.save()  # recompute state with the renewals
        changed = True
    else:
        state = compute_amm_state(amm, today=today)
        if state.differs_from(amm):
            state.apply_to(amm)
            amm._skip_signals = True
            amm.save()

    if row.excel_status and row.excel_status != amm.status:
        row.warnings.append(
            f"statut Excel « {row.excel_status} » ≠ statut calculé « {amm.status} »"
        )

    if row.errors:
        outcome = "ERROR"
    elif row.warnings:
        outcome = "WARNING"
    elif created:
        outcome = "CREATED"
    elif changed:
        outcome = "UPDATED"
    else:
        outcome = "SKIPPED"
    parts = []
    parts.append("AMM créée" if created else ("AMM mise à jour" if changed else "AMM inchangée"))
    parts.extend(row.errors)
    parts.extend(row.warnings)
    return outcome, " ; ".join(parts), amm


def _import_sheet(sheet: ParsedSheet, batch: ImportBatch | None, today: date) -> dict:
    counters = {
        key: 0
        for key in (
            "rows",
            "created",
            "updated",
            "skipped",
            "errors",
            "warnings",
            "status_mismatch",
        )
    }
    with transaction.atomic():
        country, _ = Country.objects.get_or_create(
            iso2=sheet.country_iso2, defaults={"name": sheet.country_name}
        )
        range_cache: dict = {}
        import_rows: list[ImportRow] = []
        for row in sheet.rows:
            counters["rows"] += 1
            try:
                outcome, message, amm = _apply_row(row, country, range_cache, today)
            except Exception as exc:  # unexpected data problem: keep going, report the row
                logger.exception("Erreur d'import %s!%s", sheet.name, row.row_number)
                outcome, message, amm = "ERROR", f"erreur inattendue : {exc}", None
            if outcome == "ERROR":
                counters["errors"] += 1
            elif outcome == "WARNING":
                counters["warnings"] += 1
            if "AMM créée" in message:
                counters["created"] += 1
            elif "AMM mise à jour" in message:
                counters["updated"] += 1
            elif "AMM inchangée" in message:
                counters["skipped"] += 1
            if "statut Excel" in message:
                counters["status_mismatch"] += 1
            if batch is not None:
                import_rows.append(
                    ImportRow(
                        batch=batch,
                        sheet=sheet.name,
                        row_number=row.row_number,
                        raw=row.raw,
                        outcome=outcome,
                        message=message,
                        amm=amm,
                    )
                )
        if import_rows:
            ImportRow.objects.bulk_create(import_rows, batch_size=500)
    return {"country": sheet.country_iso2, **counters}


def import_workbook(source, batch: ImportBatch | None = None, today: date | None = None) -> dict:
    """Parses and imports `source` (path or file). Returns the summary (also stored on `batch`)."""
    today = today or reference_today()
    if batch is not None:
        batch.status = ImportBatch.Status.RUNNING
        batch.reference_date = today
        batch.save(update_fields=["status", "reference_date"])
    summary: dict = {"today": today.isoformat(), "sheets": {}, "ignored_sheets": [], "totals": {}}
    try:
        with override_today(today):
            parsed = parse_workbook(source)
            summary["ignored_sheets"] = parsed.ignored
            for sheet in parsed.sheets:
                summary["sheets"][sheet.name.strip()] = _import_sheet(sheet, batch, today)
        totals: dict[str, int] = {}
        for stats in summary["sheets"].values():
            for key, value in stats.items():
                if isinstance(value, int):
                    totals[key] = totals.get(key, 0) + value
        summary["totals"] = totals
        if batch is not None:
            batch.status = ImportBatch.Status.DONE
    except Exception as exc:
        logger.exception("Import échoué")
        summary["error"] = str(exc)
        if batch is not None:
            batch.status = ImportBatch.Status.FAILED
        else:
            raise
    finally:
        if batch is not None:
            batch.summary = summary
            batch.finished_at = timezone.now()
            batch.save(update_fields=["status", "summary", "finished_at"])
    from apps.analytics.tasks import refresh_analytics_views
    from apps.core.tasks import enqueue
    from apps.realtime.publisher import publish_dashboard_refresh

    publish_dashboard_refresh()
    enqueue(refresh_analytics_views)
    return summary
