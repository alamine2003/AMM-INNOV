"""Relecture des décisions du Congo déjà rangées (1.3.6) : proposer, puis appliquer."""

import io
import json
from datetime import date
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.binders import relecture
from apps.binders.models import BinderCheck
from apps.catalog.models import Country

from .test_dossier_congo import ORIGINE, RENOUVELLEMENT

pytestmark = pytest.mark.django_db


@pytest.fixture
def congo(countries):
    return Country.objects.create(iso2="CG", name="Congo", validity_years=4)


@pytest.fixture
def page(congo, make_amm, make_renewal, make_scan):
    """Une fiche comme la 1.3.5 les rangeait : numéros de décision, dates de signature."""
    amm = make_amm(
        country=congo,
        original_number="18.716",
        original_start_date=date(2018, 3, 20),
        original_end_date=date(2022, 3, 20),
    )
    renewal = make_renewal(
        amm,
        status="OBTENU",
        number="22-0781",
        start_date=date(2022, 6, 23),
        end_date=date(2026, 6, 23),
        decision_date=date(2022, 6, 23),
    )
    scan = make_scan(amm, renewal)
    return amm, renewal, scan


def readings(texts):
    """Remplace l'OCR : le texte de chaque décision, par identifiant de document."""
    return patch.object(
        relecture,
        "extract_file",
        side_effect=lambda document: {"text": texts[document.pk], "errors": []},
    )


def test_proposal_lists_what_would_change_and_writes_nothing(page):
    amm, renewal, scan = page
    with readings({scan.pk: RENOUVELLEMENT}):
        proposals = relecture.propose()

    assert [p["product"] for p in proposals] == [amm.product.name]
    assert proposals[0]["verified"] is False
    by_slot = {period["slot"]: period for period in proposals[0]["periods"]}
    assert by_slot["renewal"]["reading"] == "code"
    assert by_slot["renewal"]["changes"] == [
        {"field": "number", "old": "22-0781", "new": "RVC-PSM-GM/09.03.3 B/N°9 JMPHS12"},
        {"field": "start_date", "old": "2022-06-23", "new": "2022-02-28"},
        {"field": "end_date", "old": "2026-06-23", "new": "2026-02-28"},
    ]
    # L'origine n'a pas de scan : ses dates seules passent au 28 février, son numéro reste.
    assert by_slot["original"]["reading"] == "sans-scan"
    assert by_slot["original"]["changes"] == [
        {"field": "start_date", "old": "2018-03-20", "new": "2018-02-28"},
        {"field": "end_date", "old": "2022-03-20", "new": "2022-02-28"},
    ]
    renewal.refresh_from_db()
    assert renewal.number == "22-0781"


def test_apply_writes_the_proposals_with_their_history(page):
    amm, renewal, scan = page
    with readings({scan.pk: RENOUVELLEMENT}):
        proposals = relecture.propose()
    report = relecture.apply(proposals)

    assert report["amms"] == 1 and report["fields"] == 5 and report["errors"] == []
    renewal.refresh_from_db()
    amm.refresh_from_db()
    assert renewal.number == "RVC-PSM-GM/09.03.3 B/N°9 JMPHS12"
    assert (renewal.start_date, renewal.end_date) == (date(2022, 2, 28), date(2026, 2, 28))
    # Début + quatre ans (durée du pays) : la fin égale la fin calculée, elle reste calculée.
    assert renewal.end_date_manual is False
    assert (amm.original_start_date, amm.original_end_date) == (
        date(2018, 2, 28),
        date(2022, 2, 28),
    )
    assert renewal.history.first().history_change_reason == relecture.REASON


def test_a_verified_page_is_left_alone_unless_asked(page, users):
    amm, renewal, scan = page
    BinderCheck.objects.create(
        amm=amm,
        result=BinderCheck.Result.CONFORME,
        checked_by=users["hq"],
        checked_at=timezone.now(),
    )
    with readings({scan.pk: RENOUVELLEMENT}):
        proposals = relecture.propose()
    assert proposals[0]["verified"] is True

    assert relecture.apply(proposals)["skipped_verified"] == 1
    renewal.refresh_from_db()
    assert renewal.number == "22-0781"

    assert relecture.apply(proposals, include_verified=True)["amms"] == 1
    renewal.refresh_from_db()
    assert renewal.number == "RVC-PSM-GM/09.03.3 B/N°9 JMPHS12"


def test_a_value_corrected_by_hand_meanwhile_is_not_overwritten(page):
    amm, renewal, scan = page
    with readings({scan.pk: RENOUVELLEMENT}):
        proposals = relecture.propose()
    renewal.number = "RVC-PSM-GM/09.03.3 B/N°9 JMPHS12 (saisi à la main)"
    renewal.save()

    report = relecture.apply(proposals)

    assert report["stale"] == 1
    renewal.refresh_from_db()
    assert renewal.number.endswith("(saisi à la main)")
    assert renewal.start_date == date(2022, 2, 28)  # le reste de la fiche est corrigé


def test_same_number_typed_with_other_spacing_is_not_a_change(page):
    amm, renewal, scan = page
    renewal.number = "RVC-PSM-GM /09.03.3 B/Nº9 JMPHS12"
    renewal.save()
    with readings({scan.pk: RENOUVELLEMENT}):
        proposals = relecture.propose()
    fields = [c["field"] for p in proposals[0]["periods"] for c in p["changes"]]
    assert "number" not in fields


def test_unreadable_code_is_reported_and_keeps_the_number(congo, make_amm, make_scan):
    amm = make_amm(
        country=congo,
        original_number="26-0466",
        original_start_date=date(2026, 8, 3),
        original_end_date=date(2030, 8, 3),
    )
    scan = make_scan(amm)
    lost = ORIGINE.replace("VC-PSM-GM /27.06.2 B/N°7 JMPHSI6\n", "")
    with readings({scan.pk: lost}):
        proposals = relecture.propose()

    period = proposals[0]["periods"][0]
    assert period["reading"] == "code-illisible"
    assert [c["field"] for c in period["changes"]] == ["start_date", "end_date"]
    assert period["changes"][1]["new"] == "2030-02-28"


def test_dates_already_on_28_february_are_not_recomputed_from_the_scan_date(
    congo, make_amm, make_scan
):
    """Essai du 19/11/2026 : une origine 2013 → 2017, dont le scan est daté de 2017, était
    proposée 2017 → 2021. Sans la clause, les années connues ne bougent pas."""
    amm = make_amm(
        country=congo,
        original_number="CV/12D-02F/09",
        original_start_date=date(2013, 2, 28),
        original_end_date=date(2017, 2, 28),
    )
    scan = make_scan(amm)
    scan.document_date = date(2017, 2, 28)
    scan.save()
    old_model = "REPUBLIQUE DU CONGO\nDECISION N° CV/12D-02F/09\nportant visa d'homologation\n"
    with readings({scan.pk: old_model}):
        assert relecture.propose() == []


def test_without_the_clause_only_the_day_moves_to_28_february(congo, make_amm, make_scan):
    amm = make_amm(
        country=congo,
        original_number="CV/12D-04F/09",
        original_start_date=date(2014, 12, 30),
        original_end_date=date(2018, 12, 30),
    )
    scan = make_scan(amm)
    old_model = "REPUBLIQUE DU CONGO\nDECISION N° CV/12D-04F/09\nportant visa d'homologation\n"
    with readings({scan.pk: old_model}):
        proposals = relecture.propose()

    assert proposals[0]["periods"][0]["changes"] == [
        {"field": "start_date", "old": "2014-12-30", "new": "2014-02-28"},
        {"field": "end_date", "old": "2018-12-30", "new": "2018-02-28"},
    ]


def test_pages_follow_the_binder_order_and_can_be_limited(congo, ranges, make_amm, make_scan):
    """Le classeur range par gamme puis par nom : la relecture suit ses numéros de page."""
    from apps.catalog.models import Product

    names = {"GENERALE": "ZINC GH", "CARDIO": "AMLODIPINE GH"}
    for code, name in names.items():
        product = Product.objects.create(name=name, range=ranges[code])
        make_amm(
            country=congo,
            product_obj=product,
            original_start_date=date(2022, 6, 23),
            original_end_date=date(2026, 6, 23),
        )
    with readings({}):
        proposals = relecture.propose()
        only_second = relecture.propose(pages=(2, 2))

    assert [(p["page"], p["product"]) for p in proposals] == [(1, "ZINC GH"), (2, "AMLODIPINE GH")]
    assert [p["page"] for p in only_second] == [2]


def test_other_countries_are_never_read(make_amm, make_scan):
    scan = make_scan(make_amm(country="SN"))
    with readings({scan.pk: ORIGINE}) as extract:
        assert relecture.propose() == []
    extract.assert_not_called()


def test_command_writes_a_report_then_applies_it(page, tmp_path):
    amm, renewal, scan = page
    report = tmp_path / "relecture.json"
    out = io.StringIO()
    with readings({scan.pk: RENOUVELLEMENT}):
        call_command("relire_congo", rapport=str(report), stdout=out)
    assert "page   1." in out.getvalue()
    assert "1 pages à corriger" in out.getvalue()
    assert "n° 22-0781 → RVC-PSM-GM/09.03.3 B/N°9 JMPHS12" in out.getvalue()
    assert json.loads(report.read_text(encoding="utf-8"))[0]["amm"] == str(amm.pk)
    renewal.refresh_from_db()
    assert renewal.number == "22-0781"

    out = io.StringIO()
    call_command("relire_congo", rapport=str(report), appliquer=True, stdout=out)
    assert "1 fiches corrigées (5 valeurs)" in out.getvalue()
    renewal.refresh_from_db()
    assert renewal.number == "RVC-PSM-GM/09.03.3 B/N°9 JMPHS12"


# --- 1.3.8 : une lecture qui contredit la saisie est montrée, pas écrite (essai du 20/11/2026)


def _origin(congo, make_amm, make_scan, **values):
    amm = make_amm(country=congo, **values)
    return amm, make_scan(amm)


def test_a_code_read_in_part_is_shown_and_never_written(congo, make_amm, make_scan):
    amm, scan = _origin(
        congo,
        make_amm,
        make_scan,
        original_number="26-0466",
        original_start_date=date(2026, 2, 28),
        original_end_date=date(2030, 2, 28),
    )
    cut = ORIGINE.replace("VC-PSM-GM /27.06.2 B/N°7 JMPHSI6", "VC-PSM-GM /27 B/N°7")
    with readings({scan.pk: cut}):
        proposals = relecture.propose()

    period = proposals[0]["periods"][0]
    assert period["reading"] == "code-partiel"
    assert period["read"].startswith("VC-PSM-GM/27")
    assert period["changes"] == []
    assert relecture.apply(proposals)["fields"] == 0


def test_a_complete_code_already_typed_wins_over_another_reading(congo, make_amm, make_scan):
    amm, scan = _origin(
        congo,
        make_amm,
        make_scan,
        original_number="VC-PSM-GM /27.06.2 B/N°1 JMPHS16",
        original_start_date=date(2026, 8, 3),
        original_end_date=date(2030, 8, 3),
    )
    with readings({scan.pk: ORIGINE}):  # l'OCR lit « N°7 »
        proposals = relecture.propose()

    period = proposals[0]["periods"][0]
    assert "diffère du Code déjà saisi" in period["doubt"]
    report = relecture.apply(proposals)
    assert report["skipped_doubtful"] == 1 and report["fields"] == 0
    amm.refresh_from_db()
    assert amm.original_number == "VC-PSM-GM /27.06.2 B/N°1 JMPHS16"
    assert amm.original_start_date == date(2026, 8, 3)  # toute la période attend le papier

    assert relecture.apply(proposals, include_doubtful=True)["fields"] == 3
    amm.refresh_from_db()
    assert amm.original_number == "VC-PSM-GM/27.06.2 B/N°7 JMPHS16"


def test_a_typed_number_missing_characters_is_completed_without_doubt(congo, make_amm, make_scan):
    amm, scan = _origin(
        congo,
        make_amm,
        make_scan,
        original_number="VC-PSM-GM/N°7 JMPHS16",
        original_start_date=date(2026, 8, 3),
        original_end_date=date(2030, 8, 3),
    )
    with readings({scan.pk: ORIGINE}):
        period = relecture.propose()[0]["periods"][0]

    assert period["doubt"] == ""
    assert period["changes"][0]["new"] == "VC-PSM-GM/27.06.2 B/N°7 JMPHS16"


def test_a_number_one_character_away_from_the_reading_waits_for_the_paper(
    congo, make_amm, make_scan
):
    amm, scan = _origin(
        congo,
        make_amm,
        make_scan,
        original_number="VCPSMGM/270623/N°2JMPHS16",
        original_start_date=date(2026, 2, 28),
        original_end_date=date(2030, 2, 28),
    )
    with readings({scan.pk: ORIGINE}):
        period = relecture.propose()[0]["periods"][0]

    assert "diffère de peu" in period["doubt"]


def test_a_decision_covering_other_years_than_the_period_waits_for_the_paper(
    congo, make_amm, make_scan
):
    """Pages 16 et 18 : origine 2014 → 2018 dont le scan est la décision 2018 → 2022."""
    amm, scan = _origin(
        congo,
        make_amm,
        make_scan,
        original_number="CV/12D-02G/09",
        original_start_date=date(2022, 2, 28),
        original_end_date=date(2026, 2, 28),
    )
    with readings({scan.pk: ORIGINE}):  # « sera renouvelée en 2030 »
        proposals = relecture.propose()

    period = proposals[0]["periods"][0]
    assert period["doubt"] == "la décision couvre 2026 → 2030, pas les années enregistrées"
    assert relecture.apply(proposals)["skipped_doubtful"] == 1
    amm.refresh_from_db()
    assert amm.original_number == "CV/12D-02G/09"
    assert amm.original_end_date == date(2026, 2, 28)


def test_a_day_moved_within_the_same_years_raises_no_doubt(page):
    amm, renewal, scan = page
    with readings({scan.pk: RENOUVELLEMENT}):
        proposals = relecture.propose()
    assert [period["doubt"] for period in proposals[0]["periods"]] == ["", ""]


def test_command_marks_doubtful_periods_and_applies_only_the_pages_asked(
    congo, ranges, make_amm, make_scan, tmp_path
):
    from apps.catalog.models import Product

    scans = {}
    for name, number in (("ALFA GH", "26-0466"), ("ZINC GH", "VC-PSM-GM/27.06.2 B/N°1 JMPHS16")):
        product = Product.objects.create(name=name, range=ranges["GENERALE"])
        amm = make_amm(
            country=congo,
            product_obj=product,
            original_number=number,
            original_start_date=date(2026, 8, 3),
            original_end_date=date(2030, 8, 3),
        )
        scans[make_scan(amm).pk] = ORIGINE
    report = tmp_path / "relecture.json"
    out = io.StringIO()
    with readings(scans):
        call_command("relire_congo", rapport=str(report), stdout=out)
    assert "À VOIR SUR LE PAPIER : le Code lu « VC-PSM-GM/27.06.2 B/N°7 JMPHS16 »" in out.getvalue()
    assert "1 périodes à voir sur le papier" in out.getvalue()

    out = io.StringIO()
    call_command("relire_congo", rapport=str(report), appliquer=True, pages="2", stdout=out)
    assert "0 fiches corrigées (0 valeurs)" in out.getvalue()
    assert "1 périodes douteuses laissées" in out.getvalue()

    out = io.StringIO()
    call_command("relire_congo", rapport=str(report), appliquer=True, stdout=out)
    assert "1 fiches corrigées (3 valeurs)" in out.getvalue()


def test_one_wrong_year_follows_the_deadline_clause_without_doubt(congo, make_amm, make_scan):
    """Page 5 (Mohamed, 20/11/2026) : fin saisie un an trop tard, la date butoir fait foi."""
    amm, scan = _origin(
        congo,
        make_amm,
        make_scan,
        original_number="VC-PSM-GM/27.06.2 B/N°7 JMPHS16",
        original_start_date=date(2026, 2, 28),
        original_end_date=date(2031, 2, 28),
        original_end_date_manual=True,
    )
    with readings({scan.pk: ORIGINE}):  # « sera renouvelée en 2030 »
        period = relecture.propose()[0]["periods"][0]

    assert period["doubt"] == ""
    assert period["changes"] == [{"field": "end_date", "old": "2031-02-28", "new": "2030-02-28"}]
