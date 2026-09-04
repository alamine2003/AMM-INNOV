"""Excel parser on a synthetic workbook, then the import service."""

from datetime import date

import pytest

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Country, Product, ProductAlias
from apps.imports.excel_parser import parse_date, parse_number, parse_workbook
from apps.imports.models import ImportBatch, ImportRow
from apps.imports.services import import_workbook
from tests.conftest import TODAY


def test_parse_workbook_sheets_and_rows(workbook_path):
    parsed = parse_workbook(str(workbook_path))
    assert [s.name for s in parsed.sheets] == ["SENEGAL ", "MALI"]
    assert {i["sheet"] for i in parsed.ignored} == {"DASHBOARD", "BENIN"}
    senegal = parsed.sheets[0]
    assert (senegal.country_iso2, senegal.country_name) == ("SN", "Sénégal")
    assert len(senegal.rows) == 5
    assert parsed.sheets[1].country_iso2 == "ML"

    row1, row2, row3, row4, _ = senegal.rows
    assert row1.product_name == "ARTEGEN 120MG PDRE SOL INJ"
    assert row1.range_code == "GENERALE" and row1.original_start_date == date(2025, 4, 28)
    assert row2.original_number == "5859" and row2.renewal_number == "5859"
    assert row2.range_code == "GENERALE" and row2.renewal_start_date == date(2025, 1, 13)
    assert row3.renewal_in_process is True and row3.range_code == "CARDIO"
    assert row3.excel_status == "IN_PROCESS" and row3.dossier_state == "INCOMPLET"
    assert row4.errors and "date illisible" in row4.errors[0]
    assert row4.range_code == "BIEN_ETRE"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("05/08/2021", date(2021, 8, 5)),
        ("05-08-2021", date(2021, 8, 5)),
        ("05.08.2021", date(2021, 8, 5)),
        ("2021-08-05", date(2021, 8, 5)),
        (None, None),
        ("", None),
    ],
)
def test_parse_date_formats(value, expected):
    assert parse_date(value) == (expected, None)


def test_parse_date_unreadable():
    value, error = parse_date("DATE ILLISIBLE")
    assert value is None and "date illisible" in error


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2021179002.0, "2021179002"),
        (5265, "5265"),
        (" E-2015-1669 ", "E-2015-1669"),
        (None, ""),
        (12.5, "12.5"),
    ],
)
def test_parse_number(value, expected):
    assert parse_number(value) == expected


@pytest.mark.django_db
def test_import_service_creates_and_is_idempotent(workbook_path, ranges):
    summary = import_workbook(str(workbook_path), today=TODAY)
    totals = summary["totals"]
    assert totals["rows"] == 7 and totals["created"] == 7 and totals["errors"] == 1
    assert {s["sheet"] for s in summary["ignored_sheets"]} == {"DASHBOARD", "BENIN"}
    assert Country.objects.filter(iso2__in=["SN", "ML"]).count() == 2
    assert MarketingAuthorization.objects.count() == 7
    # same product in two countries -> one Product, two AMM
    assert Product.objects.filter(name="ARTEGEN 120MG PDRE SOL INJ").count() == 1
    assert ProductAlias.objects.filter(raw_name="ARTEGEN 120MG PDRE SOL INJ").exists()

    by_name = {a.product.name: a for a in MarketingAuthorization.objects.select_related("product")}
    assert by_name["ARTEGEN 120MG PDRE SOL INJ"].status == "VALIDE"
    renewed = by_name["ALFA GH SR 10MG CPR B/30"]
    assert renewed.original_number == "5859"
    assert renewed.renewals.get().workflow_status == "OBTENU"
    assert renewed.effective_end_date == date(2030, 1, 13) and renewed.status == "VALIDE"
    pending = by_name["AMLO VH 10MG CPR B/30"]
    renewal = pending.renewals.get()
    assert renewal.workflow_status == "DEPOSE" and renewal.filing_date is None
    assert pending.status == "IN_PROCESS" and pending.dossier_state == "INCOMPLET"
    unreadable = by_name["GENSIL HUILE F60ML"]
    assert unreadable.status == "INDETERMINE" and unreadable.original_start_date is None
    assert by_name["KETOPROFEN GH 100MG CPR B30"].status == "EXPIRE"
    assert by_name["RAMIPRIL GH 5MG CPR B/30"].status == "EXPIRE"

    # status mismatch (Excel says VALIDE, computed EXPIRE) -> WARNING, counted
    assert summary["sheets"]["SENEGAL"]["status_mismatch"] == 1

    again = import_workbook(str(workbook_path), today=TODAY)
    assert again["totals"]["created"] == 0
    assert MarketingAuthorization.objects.count() == 7
    assert Renewal.objects.count() == 2


@pytest.mark.django_db
def test_import_batch_rows_recorded(workbook_path, ranges, users):
    batch = ImportBatch.objects.create(created_by=users["ceo"])
    import_workbook(str(workbook_path), batch=batch, today=TODAY)
    batch.refresh_from_db()
    assert batch.status == "DONE"
    rows = ImportRow.objects.filter(batch=batch)
    assert rows.count() == 7
    error = rows.get(outcome="ERROR")
    assert error.sheet == "SENEGAL " and error.row_number == 6
    assert "date illisible" in error.message
    assert rows.filter(outcome="WARNING", message__contains="statut Excel").count() == 1
