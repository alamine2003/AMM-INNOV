"""Import du manifeste des scans classés : chaque pièce rapprochée de son AMM et de sa période."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.amm.models import MarketingAuthorization, Renewal
from apps.catalog.models import Product
from apps.imports.models import ImportBatch, ImportRow
from apps.imports.scans import COLUMNS, clean_number, is_scan_manifest
from apps.imports.services import import_workbook

HEADER = list(COLUMNS.values())
counter = {"n": 0}


def folder(periode, when, numero, year=None):
    """Dossiers du classement : « 1_AMM ORIGINE - 2019 - N° 885 », « 2_RENOUVELLEMENT 1 - … »."""
    if periode == "ORIGINE":
        return f"1_AMM ORIGINE - {year or when[:4] or 'SANS DATE'} - N° {numero.replace('/', '-')}"
    if periode.startswith("RENOUVELLEMENT"):
        rank = int(periode.split()[-1])
        return f"{rank + 1}_{periode} - {when}"
    return {"DEPOT": "6_DEPOTS - COURRIERS", "VARIATION": "7_VARIATIONS - RECTIFICATIFS"}.get(
        periode, "8_RCP - ANNEXES"
    )


def piece(
    presentation, periode, kind="AMM", when="", fiabilite="haute", numero="", year=None, **extra
):
    counter["n"] += 1
    values = {
        "pays": "SENEGAL",
        "iso2": "SN",
        "gamme": "GAMME GENERALE",
        "presentation": presentation,
        "libelle": presentation,
        "periode": periode,
        "kind": kind,
        "date": when,
        "fiabilite": fiabilite,
        "numero": numero,
        "principal": "oui",
        "chemin": (
            f"1_GAMME GENERALE/SENEGAL/LOLIP/{presentation}/"
            f"{folder(periode, when, numero, year)}/{counter['n']}.pdf"
        ),
        "nom": f"{when or 'SANS DATE'} - {periode} - {presentation}.pdf",
        "sha256": f"{counter['n']:064x}",
        **extra,
    }
    return values


def manifest(path, pieces):
    lines = [";".join(HEADER)]
    for values in pieces:
        lines.append(";".join(str(values[key]) for key in COLUMNS))
    target = path / "manifeste_scans_amm_gh.csv"
    target.write_bytes(("﻿" + "\r\n".join(lines) + "\r\n").encode("utf-8"))
    return str(target)


@pytest.fixture
def batch(users):
    return ImportBatch.objects.create(created_by=users["ceo"])


@pytest.fixture
def amm(make_amm):
    return make_amm(
        "SN",
        product_obj=Product.objects.create(name="LOLIP 10MG CPR B/30"),
        original_number="885",
        original_start_date=date(2012, 3, 1),
    )


def rows(batch):
    return {r.row_number: r for r in ImportRow.objects.filter(batch=batch)}


def test_detection(tmp_path, workbook_path):
    assert is_scan_manifest(manifest(tmp_path, []))
    assert not is_scan_manifest(str(workbook_path))
    assert clean_number("9488/13 (decision 0449/2013)") == "9488/13"
    assert clean_number("2178/ 21") == "2178/21"


def test_origin_corrected_only_by_a_reliable_date(tmp_path, amm, batch):
    source = manifest(
        tmp_path,
        [
            piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-05", numero="885"),
            piece(
                "LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-05", fiabilite="lecture visuelle"
            ),
        ],
    )
    summary = import_workbook(source, batch=batch)
    assert summary["kind"] == "scans"
    amm.refresh_from_db()
    assert amm.original_start_date == date(2012, 3, 5)  # le classement fait foi
    assert amm.original_number == "885"
    placed = rows(batch)[2]
    assert placed.outcome == "UPDATED"
    assert placed.amm_id == amm.pk
    assert placed.raw["placement"]["renewal"] is None
    assert placed.raw["placement"]["kind"] == "AMM"
    assert placed.raw["placement"]["document_date"] == "2012-03-05"


def test_approximate_date_changes_nothing(tmp_path, amm, batch):
    source = manifest(
        tmp_path,
        [piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-01-01", fiabilite="approximative")],
    )
    import_workbook(source, batch=batch)
    amm.refresh_from_db()
    assert amm.original_start_date == date(2012, 3, 1)


def test_later_document_in_the_origin_folder_is_not_the_origin_date(tmp_path, amm, batch):
    source = manifest(
        tmp_path,
        [piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2023-06-09", numero="885", year="2012")],
    )
    import_workbook(source, batch=batch)
    amm.refresh_from_db()
    assert amm.original_start_date == date(2012, 3, 1)
    assert rows(batch)[2].raw["placement"]["document_date"] == "2023-06-09"


def test_classement_numbers_only_fill_an_empty_number(tmp_path, amm, make_amm, batch):
    empty = make_amm(
        "SN",
        product_obj=Product.objects.create(name="GENOPRIL 10MG CPR B/30"),
        original_number="",
        original_start_date=date(2014, 1, 2),
    )
    source = manifest(
        tmp_path,
        [
            piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-01", numero="18"),
            piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-01", numero="886"),
            piece("GENOPRIL 10MG CPR B/30", "ORIGINE", when="2014-01-02", numero="E-2014-0238"),
        ],
    )
    import_workbook(source, batch=batch)
    amm.refresh_from_db()
    empty.refresh_from_db()
    assert amm.original_number == "885"
    assert empty.original_number == "E-2014-0238"
    assert "conservé" in rows(batch)[3].message


def test_divergent_numbers_do_not_touch_the_record(tmp_path, amm, batch):
    source = manifest(
        tmp_path,
        [
            piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-01", numero="0293"),
            piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-01", numero="9864/14"),
        ],
    )
    import_workbook(source, batch=batch)
    amm.refresh_from_db()
    assert amm.original_number == "885"


def test_missing_renewal_created_and_renumbered_by_date(tmp_path, amm, make_renewal, batch):
    recent = make_renewal(amm, status="OBTENU", start_date=date(2022, 3, 1), number="R2")
    source = manifest(
        tmp_path,
        [
            piece("LOLIP 10MG CPR B/30", "RENOUVELLEMENT 1", when="2017-03-01", numero="R1"),
            piece("LOLIP 10MG CPR B/30", "RENOUVELLEMENT 2", when="2022-03-01", numero="R2"),
        ],
    )
    import_workbook(source, batch=batch)
    renewals = list(Renewal.objects.filter(amm=amm).order_by("sequence"))
    assert [(r.sequence, r.start_date) for r in renewals] == [
        (1, date(2017, 3, 1)),
        (2, date(2022, 3, 1)),
    ]
    assert renewals[1].pk == recent.pk
    amm.refresh_from_db()
    # L'échéance reste celle du dernier renouvellement, pas de la décision ajoutée après coup.
    assert amm.effective_end_date == recent.end_date
    by_line = rows(batch)
    assert by_line[2].outcome == "CREATED"
    assert by_line[2].raw["placement"]["renewal"] == str(renewals[0].pk)
    assert by_line[3].raw["placement"]["renewal"] == str(recent.pk)


def test_near_date_matches_and_reliable_date_corrects(tmp_path, amm, make_renewal, batch):
    renewal = make_renewal(amm, status="OBTENU", start_date=date(2017, 1, 15), number="R1")
    source = manifest(
        tmp_path, [piece("LOLIP 10MG CPR B/30", "RENOUVELLEMENT 1", when="2017-03-01", numero="R1")]
    )
    import_workbook(source, batch=batch)
    renewal.refresh_from_db()
    assert renewal.start_date == date(2017, 3, 1)
    assert Renewal.objects.filter(amm=amm).count() == 1


def test_pending_dossier_concluded_by_a_newer_decision(tmp_path, amm, make_renewal, batch):
    pending = make_renewal(amm, status="DEPOSE", filing_date=date(2016, 10, 1))
    source = manifest(
        tmp_path,
        [
            piece("LOLIP 10MG CPR B/30", "DEPOT", kind="RECEPISSE", when="2016-10-01"),
            piece("LOLIP 10MG CPR B/30", "RENOUVELLEMENT 1", when="2017-03-01", numero="R1"),
        ],
    )
    import_workbook(source, batch=batch)
    pending.refresh_from_db()
    assert pending.workflow_status == "OBTENU"
    assert pending.start_date == date(2017, 3, 1)
    assert Renewal.objects.filter(amm=amm).count() == 1
    deposit = rows(batch)[2]
    assert deposit.raw["placement"]["renewal"] == str(pending.pk)
    assert deposit.raw["placement"]["kind"] == "RECEPISSE"


def test_deposit_goes_with_the_renewal_it_preceded(tmp_path, amm, make_renewal, batch):
    renewal = make_renewal(amm, status="OBTENU", start_date=date(2017, 3, 1), number="R1")
    source = manifest(
        tmp_path,
        [
            piece("LOLIP 10MG CPR B/30", "DEPOT", kind="RECEPISSE", when="2016-11-20"),
            piece("LOLIP 10MG CPR B/30", "DEPOT", kind="RECEPISSE", when="2011-06-01"),
            piece("LOLIP 10MG CPR B/30", "VARIATION", kind="COURRIER", when="2018-05-02"),
            piece("LOLIP 10MG CPR B/30", "RCP", kind="AUTRE", when=""),
        ],
    )
    import_workbook(source, batch=batch)
    renewal.refresh_from_db()
    assert renewal.filing_date == date(2016, 11, 20)
    by_line = rows(batch)
    assert by_line[2].raw["placement"]["renewal"] == str(renewal.pk)
    assert by_line[3].raw["placement"]["renewal"] is None  # dépôt de la demande d'origine
    assert by_line[4].raw["placement"]["renewal"] == str(renewal.pk)  # période en vigueur
    assert by_line[5].raw["placement"]["renewal"] is None
    assert by_line[5].raw["placement"]["document_date"] == "2012-03-01"


def test_unknown_presentation_creates_product_and_amm(tmp_path, countries, ranges, batch):
    source = manifest(
        tmp_path,
        [
            piece("NOUVO 5MG CPR B/30", "ORIGINE", when="2019-07-04", numero="2178/ 21"),
            piece("NOUVO 5MG CPR B/30", "RENOUVELLEMENT 1", when="2024-07-04", numero="R-1"),
        ],
    )
    summary = import_workbook(source, batch=batch)
    amm = MarketingAuthorization.objects.get(product__name__startswith="NOUVO")
    assert amm.original_number == "2178/21"
    assert amm.original_start_date == date(2019, 7, 4)
    assert amm.renewals.get().start_date == date(2024, 7, 4)
    totals = summary["totals"]
    assert totals["amms_created"] == 1
    assert totals["renewals_created"] == 1
    assert totals["pieces_placed"] == 2


def test_dry_run_writes_nothing(tmp_path, countries, ranges, users):
    batch = ImportBatch.objects.create(created_by=users["ceo"], dry_run=True)
    source = manifest(tmp_path, [piece("NOUVO 5MG CPR B/30", "ORIGINE", when="2019-07-04")])
    summary = import_workbook(source, batch=batch, dry_run=True)
    assert not MarketingAuthorization.objects.exists()
    assert summary["totals"]["amms_created"] == 1
    row = ImportRow.objects.get(batch=batch)
    assert row.outcome == "CREATED"
    assert row.amm_id is None


def test_untracked_country_and_copies(tmp_path, amm, batch):
    source = manifest(
        tmp_path,
        [
            piece(
                "LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-01", pays="MAURITANIE", iso2="MR"
            ),
            piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-01", principal="non"),
        ],
    )
    import_workbook(source, batch=batch)
    only = ImportRow.objects.get(batch=batch)
    assert only.outcome == "WARNING"
    assert only.raw["placement"] is None


def test_api_accepts_the_manifest_csv_only(tmp_path, ceo_client, amm):
    path = manifest(tmp_path, [piece("LOLIP 10MG CPR B/30", "ORIGINE", when="2012-03-01")])
    with open(path, "rb") as handle:
        upload = SimpleUploadedFile("manifeste.csv", handle.read(), content_type="text/csv")
    response = ceo_client.post(
        "/api/v1/imports", {"file": upload, "dry_run": "true"}, format="multipart"
    )
    assert response.status_code == 202, response.content
    other = SimpleUploadedFile("autre.csv", b"a;b\n1;2\n", content_type="text/csv")
    response = ceo_client.post("/api/v1/imports", {"file": other}, format="multipart")
    assert response.status_code == 400


def test_correction_that_would_shorten_validity_is_left_for_review(tmp_path, make_amm, batch):
    # Le Dashboard porte en « origine » la dernière décision ; le classement n'a que l'AMM de 2009.
    amm = make_amm(
        "SN",
        product_obj=Product.objects.create(name="ARTRIM 15MG-90MG SIROP"),
        original_number="7572/09",
        original_start_date=date(2019, 5, 22),
    )
    source = manifest(
        tmp_path,
        [piece("ARTRIM 15MG-90MG SIROP", "ORIGINE", when="2009-05-22", numero="7572/09")],
    )
    import_workbook(source, batch=batch)
    amm.refresh_from_db()
    assert amm.original_start_date == date(2019, 5, 22)
    row = ImportRow.objects.get(batch=batch)
    assert row.outcome == "WARNING"
    assert "non appliquées" in row.message
    assert row.raw["placement"]["amm"] == str(amm.pk)


def test_more_exact_date_a_few_days_earlier_is_applied(tmp_path, make_amm, batch):
    # Bénin : le Dashboard porte le 16/04/2019, la décision classée est du 06/04/2019.
    amm = make_amm(
        "SN",
        product_obj=Product.objects.create(name="AMLO VH 10MG CPR B/30"),
        original_number="2019-4848",
        original_start_date=date(2019, 4, 16),
    )
    source = manifest(
        tmp_path,
        [piece("AMLO VH 10MG CPR B/30", "ORIGINE", when="2019-04-06", numero="2019-4848")],
    )
    import_workbook(source, batch=batch)
    amm.refresh_from_db()
    assert amm.original_start_date == date(2019, 4, 6)
    assert ImportRow.objects.get(batch=batch).outcome == "UPDATED"


def test_date_wins_over_a_reused_number(tmp_path, amm, make_renewal, batch):
    # Le Dashboard porte le n° de 2018 sur la décision de 2022 (Congo).
    dashboard = make_renewal(
        amm,
        status="OBTENU",
        start_date=date(2022, 6, 23),
        number="18.813",
        end_date=date(2026, 6, 23),
        end_date_manual=True,
    )
    source = manifest(
        tmp_path,
        [
            piece("LOLIP 10MG CPR B/30", "RENOUVELLEMENT 1", when="2018-03-22", numero="18.813"),
            piece("LOLIP 10MG CPR B/30", "RENOUVELLEMENT 2", when="2022-06-23"),
        ],
    )
    import_workbook(source, batch=batch)
    dashboard.refresh_from_db()
    assert dashboard.start_date == date(2022, 6, 23)
    assert dashboard.end_date == date(2026, 6, 23)
    first = Renewal.objects.get(amm=amm, start_date=date(2018, 3, 22))
    assert (first.sequence, dashboard.sequence) == (1, 2)


def test_manual_duration_follows_a_corrected_start(tmp_path, amm, make_renewal, batch):
    renewal = make_renewal(
        amm,
        status="OBTENU",
        start_date=date(2022, 4, 1),
        end_date=date(2026, 4, 1),
        end_date_manual=True,
    )
    source = manifest(
        tmp_path, [piece("LOLIP 10MG CPR B/30", "RENOUVELLEMENT 1", when="2022-06-23")]
    )
    import_workbook(source, batch=batch)
    renewal.refresh_from_db()
    assert (renewal.start_date, renewal.end_date) == (date(2022, 6, 23), date(2026, 6, 23))
