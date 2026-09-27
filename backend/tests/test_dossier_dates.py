"""Dates des décisions (27/09/2026) : mesure sur 1 313 dossiers réels, 530 → 616 dates justes."""

import types

import pytest

from apps.imports.dossier.preview import build_preview
from apps.imports.dossier.recognition import recognize_file, table_rows
from apps.imports.models import DossierImport

from .test_dossier_application import stored
from .test_dossier_recognition import staged

pytestmark = pytest.mark.django_db


@pytest.fixture
def batch(users):
    return DossierImport.objects.create(root_name="DOSSIER", created_by=users["hq"])


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("06 DEC. 2022*03 6986", "2022-12-06"),  # mois abrégé suivi d'un point
        ("01 juin2021*019226", "2021-06-01"),  # mois collé à l'année
        ("16.10.2014+:15490", "2014-10-16"),
        ("10.06.2016 08452", "2016-06-10"),  # sans astérisque, seul sur sa ligne
    ],
)
def test_senegal_registration_stamps(batch, stamp, expected):
    text = f"{stamp}\nREPUBLIQUE DU SENEGAL\nArrêté portant octroi de l'Autorisation de Mise sur "
    text += "le Marché\n"
    row = recognize_file(staged(batch, "SENEGAL/X/AMM.pdf", text), [], [])
    assert row["decision_date"] == expected


def test_date_next_to_the_amm_number(batch):
    text = (
        "REPUBLIQUE DU SENEGAL\nDécision portant autorisation de mise sur le marché\n"
        "Article premier.- L'autorisation de mise sur le marché (AMM) n°014477 du 07 mai 2019, "
        "accordée à la spécialité\n"
    )
    row = recognize_file(staged(batch, "SENEGAL/X/AMM.pdf", text), [], [])
    assert row["start_date"] == "2019-05-07"


def test_deposit_number_date_is_not_the_amm_date(batch):
    """Bénin : « dossier enregistré sous le n° AMM_2019_5604 du 03/03/2015 » date le dépôt."""
    text = (
        "REPUBLIQUE DU BENIN\nObjet : visa de commercialisation\n"
        "Réf. : votre dossier enregistré sous le n° AMM_2019_5604 du 03/03/2015\n"
    )
    row = recognize_file(staged(batch, "BENIN/X/AMM.pdf", text), [], [])
    assert row["start_date"] is None


def test_renewal_letter_gives_the_original_amm(users, product, countries):
    """Sénégal : « … l'AMM n° 5735 du 22/12/2010 est renouvelée pour … » (renouvellement seul)."""
    batch = DossierImport.objects.create(root_name="SENEGAL - ARTEGEN", created_by=users["hq"])
    stored(
        batch,
        "SENEGAL - ARTEGEN/RENOUVELLEMENT/AMM ARTEGEN 2015.pdf",
        "REPUBLIQUE DU SENEGAL\nMinistère de la Santé\nJ'ai l'honneur de vous faire savoir "
        "qu'une suite favorable a été réservée à votre demande de renouvellement de "
        f"l'autorisation de mise sur le marché de la spécialité {product.name}.\n"
        "En conséquence, l'AMM n° 5735 du 22/12/2010 est renouvelée pour une durée de "
        "cinq (5) ans.\nDakar, le 20/12/2015\n",
    )
    preview = build_preview(batch)
    assert preview["original"]["original_number"] == "5735"
    assert preview["original"]["original_start_date"] == "2010-12-22"


def test_senegal_commission_date_is_not_the_amm_date(batch):
    text = (
        "REPUBLIQUE DU SENEGAL\nArrêté portant octroi de l'Autorisation de Mise sur le Marché\n"
        "VU l'avis de la Commission nationale du Médicament en date du 20 août 2025 ;\n"
    )
    senegal = types.SimpleNamespace(pk=1, name="Sénégal", iso2="SN")
    row = recognize_file(staged(batch, "SENEGAL/X/AMM.pdf", text), [senegal], [])
    assert row["decision_date"] is None


def test_guinea_certificate_columns(batch):
    text = (
        "REPUBLIQUE DE GUINEE\nCertificat d'autorisation de mise sur le marché\n"
        "PGHT N° F-AMM DEBUT DE VALIDITE FIN DE VALIDITE\n7,84 EURO 5272 21/05/2024 21/05/2029\n"
    )
    row = recognize_file(staged(batch, "GUINEE/X/AMM.pdf", text), [], [])
    assert (row["start_date"], row["end_date"]) == ("2024-05-21", "2029-05-21")


def test_ivory_coast_list_date_shifted_by_ocr():
    text = (
        "Dénomination | N° de visa | Date de visa\n"
        "AMLOPERIN 5 mg/5 mg comprimés E-2013-259 | 17-07-2013\n"
        "AMLOPERIN 5 mg/10 mg comprimés | E-2013-260 | 17-07-2013\n"
        "AMLOPERIN 10 mg/5 mg comprimés E-2013-261 Perindopril\n"
        "AMLOPERIN 10 mg/10 mg comprimés | E-2013-262 | 17-07-2013\n"
    )
    rows = table_rows(text)
    assert [row["date"] for row in rows] == ["2013-07-17"] * 4
