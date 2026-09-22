"""Décisions bilingues scannées (format du Cameroun) : extraits OCR réels, noms anonymisés.

Les textes reprennent la mise en page et les fautes d'OCR constatées sur les 44 décisions
réelles (« du11/09/2018 », « Décision N419602301 », « acing (5) ans ») ; seuls les noms de
produits, de titulaires et les adresses ont été remplacés.
"""

from datetime import date

import pytest

from apps.catalog.models import Country, Product
from apps.imports.dossier.matching import folder_product, name_compatible
from apps.imports.dossier.preview import build_preview
from apps.imports.dossier.recognition import _authorization_number, _validity_period, fold
from apps.imports.models import DossierImport

from .test_dossier_recognition import staged

pytestmark = pytest.mark.django_db

HEADER = (
    "REPUBLIQUE DU CAMEROUN REPUBLIC OF CAMEROON\n"
    "Paix-Travail-Patrie Peace-Work-Fatherland\n"
    "MINISTERE DE LA SANTE PUBLIQUE MINISTRY OF PUBLIC HEALTH\n"
)

RENEWAL = HEADER + (
    "Décision N° 11380113 /D/MINSANTE/SG/DP Lsofis du... . portant\n\n"
    "RENOUVELLEMENT DE L'AUTORISATION DE MISE SUR LE MARCHE D'UN PRODUIT PHARMACEUTIQUE\n"
    "RENEWAL OF THE AUTHORIZATION TO MARKET PHARMACEUTICAL PRODUCT\n\n"
    "Article ler: Est renouvelée, l'Autorisation de Mise sur le Marché Camerounais prévu a "
    "l'article\n64 de la Loi N°90/035 du 10 Aofit 1990 accordée a\n"
    "Authorization is hereby renewed to launch on the market according to the article 64\n"
    "of Law N°90/035 of August 10, 1990 to\n\n"
    "LABO EXEMPLE. . 19/20, RUE DU TEST, PUNE - 411\n001\n\n"
    "en vue du débit a titre gratuit ou onéreux de la spécialité pharmaceutique\n"
    "for sale or free distribution of the following pharmaceutical product :\n\n"
    "EXEMPLO-GH\nDCI/INN: ARTEMETHER+LUMEFANTRINE\nDosage/Strength:15mg/90mg\n"
    "Presentation:Suspension buvable/Oral suspension, Flacon/Bottle, F1/60 ml\n"
    "Ce produit est enregistré sous le N°/Registration number : 11380113\n"
    "Art{0:La validité de cette autorisation est limitée acing (5) ans a partir du11/09/2018\n"
    "A renouveler au plus tard le 11/09/2023\n"
    "This authorization shall be valid for five (5) years from the11/09/2018\n"
    "to be renewed before 11/09/2023\n"
)

ORIGINAL = HEADER + (
    "Décision N419602301 /DIMINSANTE/SG/DPML/SDM/SH du / of ... portant / granting\n\n"
    "AUTORISATION DE MISE SUR LEMARCHE D'UN PRODUIT PHARMACEUTIQUE\n"
    "AUTHORIZATION TO MARKET A PHARMACEUTICAL PRODUCT\n\n"
    "la Loi N°90/035 du 10 Aofit 1990 est accordée a\n"
    "Authorization is hereby granted to launch on the market according to article 64\n"
    "of Law N°90/035 of August 10, 1990:\n"
    "LABO EXEMPLE PVI LID 19/20, CITY SQUARE, PUNE - 411 001,\n\n"
    "for sale or free distribution of the following pharmaceutical product :\n\n"
    "EXEMPLO 1000MG/200MG\nDCI/INN: Amoxicilline/Acide clavulanique\n"
    "Ar7; La validité de cette autorisation est limitée acing (5) ansA partir du 29/09/2023\n"
    "a renouveler au plus tard le psvoujzord Oe\n"
    "This authorization is valid for five an £rom:29/09/2023\n"
    "La demande de renouvellement de 1'AMM N° 19602301 doit &tre déposée au moins\n"
    "The application for renewal of this Marketing Authorization No. 19602301 should be\n"
)


@pytest.fixture
def cameroon(db):
    return Country.objects.create(iso2="CM", name="Cameroun")


def batch_for(users, folder):
    return DossierImport.objects.create(root_name=f"CAMEROUN - {folder}", created_by=users["hq"])


def test_noisy_numbers_are_confronted_across_mentions():
    number, variants = _authorization_number(fold(ORIGINAL), ORIGINAL)
    assert number == "19602301" and variants == ["419602301"]
    # Deux lectures proches, chacune isolée : aucune n'est retenue (pas de numéro inventé).
    text = "N’11380113\nAUTORISATION\nCe produit est enreg © N*/Registration number: 12380213\n"
    number, variants = _authorization_number(fold(text), text)
    assert number == "" and sorted(variants) == ["11380113", "12380213"]
    # Un simple numéro d'acte n'est pas un numéro d'AMM ; « N°… /AMM/ » l'est.
    assert _authorization_number("decision n° 2024/0153\n", "Décision N° 2024/0153\n")[0] == ""
    text = "N°11381207 /AMM/MINSANT\n"
    assert _authorization_number(fold(text), text)[0] == "11381207"


def test_validity_period_prefers_printed_end_and_derives_it_from_duration():
    text = (
        "la validité de cette aurorisat jar * dix huit (18) mois 4 partir\n"
        "du 22/01/2013, 6 nave r 1 plus Lard le 24/07/2014\n"
        "renewed before 24/07/2014\n"
    )
    assert _validity_period(fold(text)) == ("2013-01-22", "2014-07-24")
    # Fin illisible des deux côtés : « cinq (5) ans à partir du 29/09/2023 ».
    assert _validity_period(fold(ORIGINAL)) == ("2023-09-29", "2028-09-29")
    # Une fin illisible antérieure au début (« 28/05/2008 ») est écartée.
    text = (
        "Art.7; La validité de cette autorisation est limitée acing (5) ans a partir du "
        "29/09/2023\nA renouveler au plus tard le 28/05/2008 Iie\n"
    )
    assert _validity_period(fold(text)) == ("2023-09-29", "2028-09-29")


def test_folder_name_tolerates_finder_colons_and_typos(ranges):
    names = [
        "EXEMPLO GH 15MG/ 90MG SUSP BUV F60ML",
        "EXEMPLO GH 40MG/240MG CPR B12",
        "TESTAGEN 10MG CPR B1",
        "TESTAGEN 20MG CPR B/1",
        "TESTSET 10MG CPR B/30",
    ]
    products = [Product.objects.create(name=name) for name in names]
    found = lambda label: folder_product(["CAMEROUN", label], products)[0]  # noqa: E731
    assert found("EXEMPLO 159MG:90MG SUSP BUV F60ML").name == names[0]
    assert found("EXEMPLO GH 40MG:240MG CPR B12").name == names[1]
    assert found("TESTSET 10MG CPR B3:0").name == names[4]
    assert found("TESTAGEN 10MG CPR B1").name == names[2]
    # Une faute sur le dosage qui laisse deux présentations possibles n'identifie rien.
    assert found("TESTAGEN 30MG CPR B1") is None
    assert found("AUTRE PRODUIT 10MG") is None


def test_printed_name_must_fit_the_presentation(ranges):
    products = [
        Product.objects.create(name=name)
        for name in ("DOLEXO 50MG CPR B/30", "DOLEXO SR 75MG CPR B/30", "EXEMPLO 1G/200MG INJ F1")
    ]
    assert name_compatible("DOLEXO®", products[0], products)
    assert not name_compatible("DOLEXO SR", products[0], products)
    assert name_compatible("EXEMPLO 1000MG/200MG", products[2], products)
    assert not name_compatible("EXEMPLO 500MG/200MG", products[2], products)


def test_scanned_renewal_matches_existing_amm_and_renewal(users, cameroon, make_amm, make_renewal):
    product = Product.objects.create(name="EXEMPLO GH 15MG/ 90MG SUSP BUV F60ML")
    amm = make_amm(
        country=cameroon,
        product_obj=product,
        original_number="11380113",
        start=date(2013, 1, 22),
    )
    renewal = make_renewal(
        amm,
        "OBTENU",
        number="11380113",
        start_date=date(2018, 9, 11),
        end_date=date(2023, 9, 11),
    )
    batch = batch_for(users, "EXEMPLO 159MG:90MG SUSP BUV F60ML")
    staged(batch, f"{batch.root_name}/AMM EXEMPLO SUSPENSION.pdf", RENEWAL, "ocr", 80)
    preview = build_preview(batch)
    assert preview["can_apply"], preview["blockers"]
    assert preview["amm"]["id"] == str(amm.pk) and preview["level"] == "MEDIUM"
    [period] = preview["renewals"]
    assert period["key"] == "renewal-2018-09-11" and period["existing_id"] == str(renewal.pk)
    assert (period["number"], period["end_date"]) == ("11380113", "2023-09-11")
    assert all(change["requires_confirmation"] for change in preview["changes"])


def test_scanned_original_reads_number_dates_and_holder(users, cameroon, make_amm):
    product = Product.objects.create(name="EXEMPLO 1G/200MG IMIV PDRE SOL INJ FL/1")
    amm = make_amm(
        country=cameroon, product_obj=product, original_number="19602301", start=date(2023, 9, 29)
    )
    batch = batch_for(users, "EXEMPLO 1G200MG IMIV PDRE SOL INJ F1")
    staged(batch, f"{batch.root_name}/AMM EXEMPLO 1000MG INJ.pdf", ORIGINAL, "ocr", 80)
    preview = build_preview(batch)
    assert preview["can_apply"], preview["blockers"]
    assert preview["amm"]["id"] == str(amm.pk)
    assert preview["original"] == {
        "original_number": "19602301",
        "original_start_date": "2023-09-29",
        "original_end_date": "2028-09-29",
        "holder": "LABO EXEMPLE PVT LTD",
    }
    assert any("lectures divergentes" in warning for warning in preview["warnings"])


def test_folder_product_without_country_amm_is_reported_not_created(users, cameroon, make_amm):
    product = Product.objects.create(name="EXEMPLO 1G/200MG IMIV PDRE SOL INJ FL/1")
    make_amm(country="SN", product_obj=product)
    batch = batch_for(users, "EXEMPLO 1G200MG IMIV PDRE SOL INJ F1")
    staged(batch, f"{batch.root_name}/AMM.pdf", ORIGINAL, "ocr", 80)
    preview = build_preview(batch)
    assert not preview["can_apply"] and preview["amm"]["id"] is None
    assert any("Aucune AMM Cameroun" in item for item in preview["blockers"])


def test_decision_naming_another_presentation_blocks(users, cameroon, make_amm):
    target = Product.objects.create(name="EXEMPLO 500MG/200MG IMIV PDRE SOL INJ FL/1")
    make_amm(country=cameroon, product_obj=target)
    batch = batch_for(users, "EXEMPLO 500MG200MG IMIV PDRE SOL INJ F1")
    staged(batch, f"{batch.root_name}/AMM.pdf", ORIGINAL, "ocr", 80)
    preview = build_preview(batch)
    assert not preview["can_apply"]
    assert any("ne correspond pas" in item for item in preview["blockers"])


def test_printed_product_line_alone_never_creates_a_product(users, cameroon):
    batch = batch_for(users, "DOSSIER INCONNU")
    staged(batch, f"{batch.root_name}/AMM.pdf", ORIGINAL, "ocr", 80)
    preview = build_preview(batch)
    assert not preview["can_apply"]
    assert any("Produit absent du catalogue" in item for item in preview["blockers"])


def test_renewal_on_the_recorded_origin_date_is_blocked(users, cameroon, make_amm):
    product = Product.objects.create(name="EXEMPLO GH 15MG/ 90MG SUSP BUV F60ML")
    make_amm(country=cameroon, product_obj=product, start=date(2018, 9, 11))
    batch = batch_for(users, "EXEMPLO GH 15MG:90MG SUSP BUV F60ML")
    staged(batch, f"{batch.root_name}/AMM.pdf", RENEWAL, "ocr", 80)
    preview = build_preview(batch)
    assert not preview["can_apply"]
    assert any("même jour que l'AMM d'origine" in item for item in preview["blockers"])
