"""Décisions des autres pays (Sénégal, Mali, Gambie, Togo, Bénin, Congo, Côte d'Ivoire, Guinée,
Tchad, Mauritanie) : extraits OCR courts reprenant la mise en page réelle, noms anonymisés.

Mesuré sur les 2 350 scans réels (1 216 dossiers produits présents dans l'Excel de référence) :
le numéro d'AMM est retrouvé pour 75 % d'entre eux, dont 90 % égaux à l'Excel.
"""

from datetime import date

import pytest

from apps.catalog.models import Country, Product
from apps.imports.dossier.matching import pick_table_row
from apps.imports.dossier.preview import build_preview
from apps.imports.dossier.recognition import parse_date, recognize_file, table_rows
from apps.imports.models import DossierImport

from .test_dossier_recognition import staged

pytestmark = pytest.mark.django_db


def read(batch, text, name="AMM.pdf", source="ocr"):
    upload = staged(batch, f"{batch.root_name}/{name}", text, source, 80)
    return recognize_file(upload, list(Country.objects.all()), list(Product.objects.all()))


@pytest.fixture
def batch(users):
    return DossierImport.objects.create(root_name="DOSSIER", created_by=users["hq"])


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("16 AVR 2019", "2019-04-16"),
        ("09 Déc. 2019", "2019-12-09"),
        ("1er juin 2020", "2020-06-01"),
        ('22" July 2019', "2019-07-22"),
        ("22nd July 2019", "2019-07-22"),
        ("24 SEP 2020", "2020-09-24"),
    ],
)
def test_abbreviated_and_ordinal_dates(printed, expected):
    assert parse_date(printed) == expected


def test_senegal_numero_amm_with_validity_range(batch):
    text = (
        "REPUBLIQUE DU SENEGAL\nMinistère de la Santé et de l'Action sociale\n"
        "Direction de la Pharmacie et du Médicament\n"
        "Prix public : 4919 F CFA.\n"
        "Numéro AMM : 0003/CN/06/2019 du 09 Déc. 2019 au 08 Déc. 2024\n"
    )
    row = read(batch, text)
    assert row["official"] and row["number"] == "0003/CN/06/2019"
    assert (row["start_date"], row["end_date"]) == ("2019-12-09", "2024-12-08")


def test_senegal_arrete_sous_le_numero(batch):
    text = (
        "REPUBLIQUE DU SENEGAL N° /MSAS/DGS/DPM\n"
        "Analyse : arrêté portant octroi de l'Autorisation de Mise sur le Marché à la spécialité\n"
        "ARRETE:\nArticle premier.- L'Autorisation de Mise sur le Marché est accordée à la "
        "spécialité :\n"
        "EXEMPLO GH 100mg suspension buvable fl/120ml\nSous le numéro : 7897\n"
    )
    assert read(batch, text)["number"] == "7897"


def test_mali_renewal_keeps_the_new_number_and_its_start(batch):
    text = (
        "REPUBLIQUE DU MALI\nDIRECTION DE LA PHARMACIE ET DU MEDICAMENT\n"
        "Bamako, le 24 SEP 2020\n"
        "Objet: Renouvellement AMM de EXEMPLO 0,3 % goutte, flacon de 5 mL\n"
        "Autorisation de Mise sur le Marché (AMM) des produits à usage humain\n"
        "j'ai l'honneur de vous informer que AMM N° 2015-654 de votre specialite\n"
        "pharmaceutique EXEMPLO 0.3% goutte, est renouvelée sous le numero\n"
        "0374R/09/2020 et le Prix Grossiste Hors Taxe est de 983,94 FCFA pour une\n"
        "periode de cinq (5) ans a compter du 1er juin 2020,\n"
    )
    row = read(batch, text)
    assert row["number"] == "0374R/09/2020"
    assert row["start_date"] == "2020-06-01" and row["period"].startswith("renewal")
    assert row["decision_date"] == "2020-09-24"


def test_gambia_registration_letter(batch):
    text = (
        "MEDICINES CONTROL AGENCY\n54 Kairaba Avenue, The Gambia.\n"
        "SUBJECT: APPROVAL FOR THE REGISTRATION OF EXEMPLO 10MG/10MG\n"
        "Registration number: MCA/Med 025/03/19\n"
        'Registration date: 20" March 2019\n'
        'Registration expiry date: 20°" March 2024\n'
    )
    row = read(batch, text)
    assert row["official"] and row["number"] == "MCA/MED 025/03/19"
    assert (row["start_date"], row["end_date"]) == ("2019-03-20", "2024-03-20")


def test_togo_sp_tg_number_and_signature_date(batch):
    text = (
        "REPUBLIQUE TOGOLAISE\nMinistère de la Santé et de l'Hygiène Publique\n"
        "N° 120 2024 /MSHP/CAB/SG/DPML Lomé, le 20 FEV 2024\n"
        "AUTORISATION DE MISE SUR\nLE MARCHE AU TOGO\n(Enregistrement)\n"
        "sont autorisés à introduire en République togolaise, leur produit pharmaceutique "
        "suivant:\n"
        "SP.TG 5223 EXEMPLO\n"
    )
    row = read(batch, text)
    assert row["number"] == "SP.TG 5223"


def test_benin_visa_de_commercialisation(batch):
    text = (
        "MINISTERE DE LA SANTE BENIN\nREPUBLIQUE DU BENIN\n"
        "COTONOU, le 16 AVR 2019\n"
        "OBJET : VISA DE COMMERCIALISATION DES LABORATOIRES EXEMPLE\n"
        "REF.: Votre dossier enregistré sous le N° AMM_2019_4848_EG du 24/01/2017\n"
        "J'ai l'honneur de vous faire parvenir le visa de commercialisation au Bénin\n"
    )
    row = read(batch, text, "Visa EXEMPLO.pdf")
    assert row["official"] and row["number"] == "2019_4848_EG"
    assert row["decision_date"] == "2019-04-16"


def test_congo_decision_number_is_the_homologation_number(batch):
    text = (
        "MINISTERE DE LA SANTE REPUBLIQUE DU CONGO\nDIRECTION DE LA PHARMACIE\n"
        "DECISION N° CV/04C-07G/09\nPortant homologation de EXEMPLO 10/12,5/160 COMPRIMES\n"
        "Le visa d'homologation du produit (enregistrement et autorisation de mise sur le marché)"
        " est accordé\n"
    )
    assert read(batch, text)["number"] == "CV/04C-07G/09"


def test_temporary_import_authorisation_is_an_annex(batch):
    text = (
        "République Islamique de Mauritanie\nMinistère de la Santé\n"
        "Objet : Autorisation Temporaire d'Importation (ATI)\n"
        "Nous venons par la présente donner notre accord pour l'importation temporaire\n"
    )
    row = read(batch, text, "ATI Mauritanie 2018.pdf")
    assert not row["official"] and row["kind"] == "AUTRE" and row["temporary_import"]


IVORY_COLUMNS = (
    "REPUBLIQUE DE COTE D'IVOIRE\nAbidjan, le 04 OCT. 2019\n"
    "Le visa d'enregistrement est accordé aux produits pharmaceutiques ci-après désignés pour une\n"
    "période renouvelable de 5 ans à compter de la date du visa :\n"
    "Dénomination\nN° de visa\nDate de visa\n"
    "EXEMPLO-GH 100 mg\nE-2019-0906\n06/02/2019\n"
    "EXEMPLO-GH 300 mg\nE-2019-0907\n06/02/2019\n"
    "AUTRE-GH 10 mg SR comprimés | E-2015-1669 | 13/01/16 Alfuzosine Liste I 7.215,52\n"
)
GUINEA_ROWS = (
    "ARRETE A /2022/ MSHP/SGG\nPortant Autorisation de Mise sur le Marché (AMM) des Spécialités\n"
    "Vu la Loi L/2018/024/AN du 20 juin 2018, relative aux Médicaments ;\n"
    "N° DESIGNATION PGHT N° AMM\n"
    "1 EXEMPLO 5MG+12,5MG+160MG COMPRIMES B/30 12,0€ 5879\n"
    "2 EXEMPLO 5MG+25MG+160MG COMPRIMES B/30 12,0€ 5880\n"
    "3 AUTRE 20MG COMPRIMES B/30 2,00€ 5886\n"
    "4 AUTRE SIROP FL/200ML 5 EURO 6261 10/09/2025 10/09/2030\n"
)


def test_grouped_tables_in_rows_or_in_columns():
    ivory = table_rows(IVORY_COLUMNS)
    assert [(row["label"], row["number"], row["date"]) for row in ivory] == [
        ("EXEMPLO-GH 100 mg", "E-2019-0906", "2019-02-06"),
        ("EXEMPLO-GH 300 mg", "E-2019-0907", "2019-02-06"),
        ("AUTRE-GH 10 mg SR comprimés", "E-2015-1669", "2016-01-13"),
    ]
    guinea = table_rows(GUINEA_ROWS)
    assert [row["number"] for row in guinea] == ["5879", "5880", "5886", "6261"]
    assert guinea[0]["label"] == "EXEMPLO 5MG+12,5MG+160MG COMPRIMES B/30"
    assert guinea[3]["date"] == "2025-09-10"
    # Une décision ordinaire n'est pas un tableau.
    assert table_rows("Sous le numéro : 7897\nFait à Dakar, le 16 décembre 2019\n") == []


def test_pick_table_row_uses_the_presentation():
    products = [
        Product.objects.create(name="EXEMPLO 5MG/12,5MG/160MG CPR B/30"),
        Product.objects.create(name="EXEMPLO 5MG/25MG/160MG CPR B/30"),
    ]
    rows = table_rows(GUINEA_ROWS)
    assert pick_table_row(rows, products[1], products)["number"] == "5880"
    assert pick_table_row(rows, products[0], products)["number"] == "5879"
    other = Product.objects.create(name="ABSENT 10MG CPR B/30")
    assert pick_table_row(rows, other, [*products, other]) is None


def test_grouped_decision_in_each_product_folder_is_read_on_its_own_line(users, make_amm):
    guinea = Country.objects.get(iso2="GN")
    target = Product.objects.create(name="EXEMPLO 5MG/25MG/160MG CPR B/30")
    sibling = Product.objects.create(name="EXEMPLO 5MG/12,5MG/160MG CPR B/30")
    amm = make_amm(
        country=guinea, product_obj=target, original_number="5880", start=date(2022, 12, 30)
    )
    make_amm(country=guinea, product_obj=sibling, original_number="5879")
    batch = DossierImport.objects.create(
        root_name="GUINEE - EXEMPLO 5MG25MG160MG CPR B30", created_by=users["hq"]
    )
    staged(batch, f"{batch.root_name}/Documents communs/AMM Guinée 39 PRODUITS.pdf", GUINEA_ROWS)
    preview = build_preview(batch)
    assert preview["can_apply"], preview["blockers"]
    assert preview["amm"]["id"] == str(amm.pk)
    assert preview["original"]["original_number"] == "5880"


def test_grouped_decision_without_the_product_is_kept_as_annex(users, make_amm):
    guinea = Country.objects.get(iso2="GN")
    target = Product.objects.create(name="ABSENT 10MG CPR B/30")
    make_amm(country=guinea, product_obj=target, original_number="1234")
    batch = DossierImport.objects.create(
        root_name="GUINEE - ABSENT 10MG CPR B30", created_by=users["hq"]
    )
    staged(batch, f"{batch.root_name}/Documents communs/AMM Guinée.pdf", GUINEA_ROWS)
    preview = build_preview(batch)
    assert any("décision groupée" in point["message"] for point in preview["review_points"])
    assert preview["original"].get("original_number") in (None, "")


def test_guinea_single_certificate_table():
    text = (
        "REPUBLIQUE DE GUINEE\nCERTIFIE\nArticle premier : L'Autorisation de Mise sur le Marché "
        "(AMM) est accordée au produit pharmaceutique\n"
        "Désignation EXEMPLO 10MG+10MG COMPRIME B/100\n"
        "PGHT N° E-AMM Début de validité Fin de validité\n"
        "22 EURO 5264 21/05/2024 21/05/2029\n"
    )
    batch = DossierImport.objects.create(root_name="GUINEE - EXEMPLO")
    row = read(batch, text)
    assert row["number"] == "5264"
    assert (row["start_date"], row["end_date"]) == ("2024-05-21", "2029-05-21")


def test_row_of_a_sibling_presentation_is_never_taken():
    products = [
        Product.objects.create(name="EXEMPLO GH 5MG CPR B/28"),
        Product.objects.create(name="EXEMPLO GH 10MG CPR B/28"),
    ]
    rows = [
        {"label": "EXEMPLO-GH 5MG COMPRIME B/28", "number": "5125", "date": None},
        {"label": "EXEMPLO-GH 10MG COMPRIME B/28", "number": "5126", "date": None},
        {"label": "AUTRE 20MG COMPRIME B/30", "number": "5127", "date": None},
    ]
    assert pick_table_row(rows, products[1], products)["number"] == "5126"
    assert pick_table_row(rows, products[0], products)["number"] == "5125"
