"""1.2.5 : dossiers du classement AMM GHPL déposés sans leur dossier pays.

Cas réel du 11/11/2026 : « METRO-GH » déposé seul (dossier de Côte d'Ivoire), découpé en
« METRO-GH 500MG CPR B30 - 1_AMM ORIGINE - 2016 - N° E-2015-2001 », « … - 4_DEPOTS - COURRIERS »,
scan illisible : « Pays non reconnu », et « COURRIERS » pris pour un produit.
"""

from datetime import date

import pytest

from apps.catalog.models import Country, Product
from apps.imports.dossier.identification import _folder_label
from apps.imports.dossier.preview import build_preview
from apps.imports.models import DossierImport

from .test_dossier_recognition import staged

pytestmark = pytest.mark.django_db


def codes(preview) -> list[str]:
    return (preview["question"] or {}).get("codes", [])


@pytest.fixture
def metro(make_amm, ranges):
    ivory = Country.objects.get(iso2="CI")
    product = Product.objects.create(name="METRO-GH 500MG CPR B/30", range=ranges["GENERALE"])
    amm = make_amm(
        country=ivory, product_obj=product, original_number="E-2015-2001", start=date(2016, 3, 1)
    )
    # La même présentation au Sénégal, sous un autre n° : seul le n° départage les deux pays.
    make_amm(country="SN", product_obj=product, original_number="9876", start=date(2016, 5, 2))
    return amm


def test_country_comes_from_product_and_number_when_the_folder_does_not_say_it(users, metro):
    batch = DossierImport.objects.create(
        root_name="METRO-GH - METRO-GH 500MG CPR B30 - 1_AMM ORIGINE - 2016 - N° E-2015-2001",
        created_by=users["hq"],
    )
    staged(batch, f"{batch.root_name}/2016-03-01 - AMM - METRO.pdf", "", "ocr", 0)
    preview = build_preview(batch)
    assert "country" not in codes(preview)
    assert preview["amm"]["id"] == str(metro.pk)
    assert any("Côte d'Ivoire" in decision for decision in preview["decisions"])


def test_number_alone_never_chooses_the_country(users, metro):
    """Le n° de l'AMM ivoirienne sous un autre produit : pas de pays déduit."""
    batch = DossierImport.objects.create(
        root_name="AUTRE PRODUIT 10MG - 1_AMM ORIGINE - 2016 - N° E-2015-2001",
        created_by=users["hq"],
    )
    staged(batch, f"{batch.root_name}/scan.pdf", "", "ocr", 0)
    assert "country" in codes(build_preview(batch))


@pytest.mark.parametrize(
    "root",
    [
        "METRO-GH - METRO-GH 500MG CPR B30 - 4_DEPOTS - COURRIERS",
        "METRO-GH - METRO-GH 500MG CPR B30 - _DOCUMENT COMPLET (avant separation)",
        "METRO-GH - METRO-GH 500MG CPR B30 - 1_AMM ORIGINE - 2016 - N° E-2015-2001",
        "METRO-GH - METRO-GH 500MG CPR B30 - 2_RENOUVELLEMENTS - RENOUVELLEMENT 2 - 2021-03-01",
    ],
)
def test_classement_sections_never_name_the_product(root):
    batch = DossierImport(root_name=root)
    assert _folder_label(batch, None) == "METRO-GH 500MG CPR B30"
