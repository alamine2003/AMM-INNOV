"""Congo (1.3.6) : le numéro d'AMM est le « Code » de l'article 2, les périodes vont d'un
28 février à un 28 février.

Règles données par Mohamed le 19/11/2026, classeur papier en main, et relevées sur ses pages
vérifiées du classeur Congo. Les textes ci-dessous sont ceux que la lecture automatique a tirés
de deux décisions réelles (CEFIXIM-GH 100 mg/5 ml, 2026 ; ARTHRIM GH 80/480, renouvellement de
2022), fautes de lecture comprises.
"""

import shutil
import uuid
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from apps.imports.dossier import extraction
from apps.imports.dossier.recognition import recognize_file
from apps.imports.dossier.recognition.dates import congo_period
from apps.imports.dossier.recognition.numbers import congo_code, congo_code_complete
from apps.imports.dossier.recognition.text import fold

from .test_dossier_recognition import batch, staged  # noqa: F401 — fixture

pytestmark = pytest.mark.django_db

CONGO = SimpleNamespace(pk=uuid.uuid4(), name="Congo", iso2="CG")

ORIGINE = """MINISTERE DE LA SANTE REPUBLIQUE DU CONGO
ET DE LA POPULATION Unité-Travail-Progrés
DIRECTION DE LA PHARMACIE
ET DU MEDICAMENT
B.P. : 1635 BRAZZAVILLE

pectsron N°__2 6 -0 4 6 6 ymsp/pesssa/DPM-26
PORTANT HOMOLOGATION DE :
CEFIXIM-GH 100mg/5ml,
Poudre pour suspension buvable, boite de 1 flacon de 100m!

Le Directeur Général des Soins et Service de Santé
DECIDE
\f
Article premier =
Est accordée, aprés homologation, une autorisation de mise sur le marché de la spécialité
pharmaceutique : CEFIXIM-GH 100mg/Smil (Céfixime 100mg)/Smi, boite de 1 flacon de
100ml contenant de la poudre pour suspension buvable.

Article 2:
Les références de autorisation de mise sur le marché sont
Code
VC-PSM-GM /27.06.2 B/N°7 JMPHSI6

Titulaire et exploitant
GENERIC HEALTHCARE PVT LTD
\f
Article 8 :
La présente autorisation, & la demande de son titulaire, sera renouvelée en 2030 avant la
date butoir du 28 février. En cas contraire, elle devient caduque, sauf cas de force majeur
‘empéchant le fonctionnement régulier des services du ministére de la santé, le 1" avril
2030.

Article 9 :
La présente décision prend effet à compter de sa date de signature. /-

Fait & Brazzaville, le

Pour le directeur général des soins et service
de santé, par délégation
"""

RENOUVELLEMENT = """MINISTERE DE LA SANTE ET REPUBLIQUE DU CONGO
DE LA POPULATION, Unité*Travail*Progrès
DIRECTION DE LA PHARMACIE ET
DU MEDICAMENT
B.P. : 1635 BRAZZAVILLE

DECISION N°__2 2-0 7 8 1 /MSP/DGSSSa/DPM-22
PORTANT PROROGATION DE L'HOMOLOGATION DE : ARTHRIM GH
80/480, Comprimé, boîte de 6.

DECIDE
\f
Article premier :
Est accordé, après prorogation de l'homologation, un renouvellement de l'autorisation de
mise sur le marché de : ARTHRIM GH 80/480 (Artémether & Luméfantrine
80mg/480mg), boite de 6 comprimés.
Article 2 :
Les références du renouvellement de cette autorisation de mise sur le marché sont :
Code: RVC -PSM- GM / 09.03.3 B/N° 9 JMPHS12

Titulaire :
GENERIC HEALTHCARE PVT LTD.,

Article 3 :
Les dispositions de la décision N° 18.716/MSP/DGMPL/DPM-18 du 20 MARS 2018, dont
le code produit est VC-PSM-GM/03.01.4 B/N°1 LOPOEHS8, non contraires demeurent
inchangées.
Article 4 :
La présente autorisation, sur demande de son titulaire sera renouvelée en 2026 à la
date butoir du 28 février. Elle devient caduque, sauf cas de force majeur empêchant le
fonctionnement régulier des services du ministère de la santé, le 1er avril 2026.
Article 5 :
La présente décision, dont la validité court à compter de la date de dépôt du dossier,
prend effet à compter de sa date de signature. /-

Fait à Brazzaville, le 23 JUIN 2022
Pour le ministre de la santé et par autorisation,
"""


def read(batch, path, text):  # noqa: F811
    return recognize_file(staged(batch, path, text, source="ocr", confidence=80), [CONGO], [])


def test_origin_number_is_the_code_and_period_runs_from_28_february(batch):  # noqa: F811
    row = read(batch, "CONGO/CEFIXIM/2026-08-03 - AMM ORIGINE.pdf", ORIGINE)

    assert row["number"] == "VC-PSM-GM/27.06.2 B/N°7 JMPHS16"  # pas « 26-0466 », n° de l'acte
    assert row["number_variants"] == []
    assert (row["start_date"], row["end_date"]) == ("2026-02-28", "2030-02-28")
    assert row["period"] == "original"


def test_renewal_number_is_its_own_code_not_the_origin_one(batch):  # noqa: F811
    row = read(batch, "CONGO/ARTRIM/2022-06-23 - RENOUV.pdf", RENOUVELLEMENT)

    assert row["number"] == "RVC-PSM-GM/09.03.3 B/N°9 JMPHS12"  # pas « 22-0781 »
    assert (row["start_date"], row["end_date"]) == ("2022-02-28", "2026-02-28")
    assert row["decision_date"] == "2022-06-23"  # la signature reste la date de la décision
    assert row["period"].startswith("renewal-")
    assert row["cited_original"] == {
        "number": "VC-PSM-GM/03.01.4 B/N°1 LOPOEHS8",
        "start_date": "2018-02-28",
    }


def test_unreadable_code_gives_no_number_rather_than_the_decision_one(batch):  # noqa: F811
    """Ligne du Code perdue à la lecture : numéro vide, à relever sur le papier."""
    text = ORIGINE.replace("VC-PSM-GM /27.06.2 B/N°7 JMPHSI6\n", "")
    row = read(batch, "CONGO/CEFIXIM/2026-08-03 - AMM ORIGINE.pdf", text)

    assert row["number"] == ""
    assert (row["start_date"], row["end_date"]) == ("2026-02-28", "2030-02-28")


def test_old_congo_model_keeps_its_visa_number_with_february_dates(batch):  # noqa: F811
    """Ancien modèle (« visa d'homologation ») : le numéro de la décision est bien l'AMM."""
    text = (
        "REPUBLIQUE DU CONGO\nMINISTERE DE LA SANTE\n"
        "DECISION N° CV/12D-02C/09\nportant visa d'homologation de la spécialité\n"
        "BONCIPRO 0,3% collyre\nFait à Brazzaville, le 14 mars 2013\n"
    )
    row = read(batch, "CONGO/BONCIPRO/AMM.pdf", text)

    assert row["number"] == "CV/12D-02C/09"
    assert (row["start_date"], row["end_date"]) == ("2013-02-28", "2017-02-28")


def test_other_countries_are_untouched(batch):  # noqa: F811
    text = (
        "REPUBLIQUE DU SENEGAL\nArrêté portant octroi de l'Autorisation de Mise sur le Marché\n"
        "AMM N° 5735 du 22/12/2010\nFait à Dakar, le 22 décembre 2010\n"
    )
    row = recognize_file(staged(batch, "SENEGAL/X/AMM.pdf", text), [CONGO], [])

    assert row["start_date"] != "2010-02-28"
    assert row["end_date"] is None


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("Code : VC-PSM-GM /27.06.2 B/N°7 JMPHS16", "VC-PSM-GM/27.06.2 B/N°7 JMPHS16"),
        ("Code: RVC -PSM- GM / 09.03.3 B/N° 9 JMPHS12", "RVC-PSM-GM/09.03.3 B/N°9 JMPHS12"),
        ("Code\n    VC-PSM-GM/27.06.2.B/N°1 JMPHS15", "VC-PSM-GM/27.06.2 B/N°1 JMPHS15"),
        ("code : rvc-psm-gm/24.02.1 b/nº6 lophsI0", "RVC-PSM-GM/24.02.1 B/N°6 LOPHS10"),
        ("dont le\ncode produit est VC-PSM-GM/03.01.4 B/N°1 LOPOEHS8, non", ""),
        # Fautes de lecture relevées sur le serveur le 19/11/2026.
        ("Code: RVC -PSM- GM / 09.033 B/N? 1 JMPHSI2", "RVC-PSM-GM/09.03.3 B/N°1 JMPHS12"),
        ("Code: RVC -PSM- GM / 09.03.3 B/N®° 1 JMPHS12", "RVC-PSM-GM/09.03.3 B/N°1 JMPHS12"),
        ("Code : RVC-PSM-GM/02.245-B/N? 4 AAE HS 8", "RVC-PSM-GM/02.24.5 B/N°4 AAE HS 8"),
        ("Code : RVC-PSM-GM/02.24.5 - B/N°L AAE HS 8", "RVC-PSM-GM/02.24.5 B/N°1 AAE HS 8"),
        ("Code : VC-PSM-GM Y27.06.2 B/N°4 JMPHS15", "VC-PSM-GM/27.06.2 B/N°4 JMPHS15"),
        # Essai du 20/11/2026 : un point lu comme une virgule coupait le Code à « …/24 ».
        ("Code : RVC-PSM-GM/24,02.1 B/N°4 LOPHS10", "RVC-PSM-GM/24.02.1 B/N°4 LOPHS10"),
        ("Code : VC-PSM-GM /3, 03.1 B/N°1 LOPOEHS8", "VC-PSM-GM/3.03.1 B/N°1 LOPOEHS8"),
        ("Code : RVC-PSM-GM/09.03.3 B/N°10 TMPHS12", "RVC-PSM-GM/09.03.3 B/N°10 JMPHS12"),
        ("Code : RVC-PSM-GM/09.03.3 B/N°10JMPHS12", "RVC-PSM-GM/09.03.3 B/N°10 JMPHS12"),
        ("Code : VC-PSM-GM/27.06.2 B/N°7 IMPHS16", "VC-PSM-GM/27.06.2 B/N°7 JMPHS16"),
    ],
)
def test_code_line_readings(printed, expected):
    text = f"Article 2 :\n{printed}\nTitulaire :\n"
    assert congo_code(fold(text), text) == expected


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("VORSM-ÈM/3.03.1 B/N°3 LOPOEHS8", "VC-PSM-GM/3.03.1 B/N°3 LOPOEHS8"),
        ("VE-PSA-GM/3,03.1 B/N°2 LOPOEHS8", "VC-PSM-GM/3.03.1 B/N°2 LOPOEHS8"),
        ("RVC-PSM-6M/29.03.2 B/N°3 JMPHS12", "RVC-PSM-GM/29.03.2 B/N°3 JMPHS12"),
    ],
)
def test_fixed_parts_of_a_fully_read_code_are_restored(printed, expected):
    """Essai du 20/11/2026 : la référence est lue en entier, le préfixe est déformé."""
    text = (
        "Article 2 : Les références de l'autorisation de mise sur le marché sont :\n"
        f"Code : {printed}\nTitulaire :\n"
    )
    assert congo_code(fold(text), text) == expected


@pytest.mark.parametrize(
    ("value", "complete"),
    [
        ("VC-PSM-GM/27.06.2 B/N°7 JMPHS16", True),
        ("VC-PSM-GM /12.09.1 B/Nº3 JMPHS12", True),  # saisi à la main, autre ponctuation
        ("VC-PSM-GM/27.06.2.B/N°1 JMPHS15", True),
        ("RVC-PSM-GM/02.24.5 B/N°6 AAE HS 8", True),
        ("RVC-PSM-GM/24", False),
        ("VC-PSM-GM/N°9 JMPHS16", False),
        ("VCPSMGM/0807023/N°2JMPHS16", False),
        ("26-0466", False),
        ("CV/12D-02G/09", False),
        ("", False),
    ],
)
def test_a_complete_code_has_its_four_parts(value, complete):
    assert congo_code_complete(value) is complete


def test_an_unknown_signatory_is_kept_as_read():
    """Un sigle à plus d'une lettre des sigles connus n'est pas rapproché d'eux."""
    text = "Article 2 :\nCode : VC-PSM-GM/27.06.2 B/N°7 XYPHS16\nTitulaire :\n"
    assert congo_code(fold(text), text) == "VC-PSM-GM/27.06.2 B/N°7 XYPHS16"


def test_period_without_the_clause_uses_the_decision_year():
    assert congo_period("texte sans la clause", "2020-03-24") == ("2020-02-28", "2024-02-28")
    assert congo_period("texte sans la clause", None) is None
    # Année illisible après « renouvelée en » : celle de la caducité (« le 1er avril 2030 »).
    clause = "sera renouvelee en 20 avant la date butoir du 28 fevrier ... le 1er avril 2030."
    assert congo_period(clause, "2026-08-03") == ("2026-02-28", "2030-02-28")


# --- Lecture des lignes surlignées -------------------------------------------------------------


def page(highlight: bool, size=(1240, 400)):
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    if highlight:
        draw.rectangle((60, 180, 900, 240), fill=(250, 190, 70))  # surligneur orange
    return image, draw


def test_highlighter_is_detected_but_coloured_writing_is_not():
    marked, _ = page(highlight=True)
    assert extraction._highlighted(marked)

    written, draw = page(highlight=False)
    for y in range(40, 380, 30):  # lignes d'écriture fines, rouges et bleues
        draw.line((60, y, 1100, y), fill=(220, 40, 60) if y % 60 else (60, 150, 220), width=2)
    assert not extraction._highlighted(written)


def test_lines_seen_only_by_the_second_reading_are_added_in_place():
    base = "Article 2 :\nLes références sont :\nCode\n\nTitulaire et exploitant\n"
    code = "VC-PSM-GM /27.06.2 B/N°7 JMPHS16"
    extra = f"Article 2:\nLes references sont :\nCode\n{code}\nTitulaire et exploitant\n"
    merged = extraction._merge_readings(base, extra).splitlines()

    assert merged.count(code) == 1
    assert merged.index("Code") < merged.index(code)
    assert merged.index("VC-PSM-GM /27.06.2 B/N°7 JMPHS16") < merged.index(
        "Titulaire et exploitant"
    )
    assert len(merged) == len(base.splitlines()) + 1  # rien d'autre n'est doublé


def test_on_a_highlighted_page_our_reading_comes_before_the_scanner_one():
    """PDF « cherchable » : le texte posé par le scanner déforme la ligne surlignée (relevé sur
    le serveur le 19/11/2026). Notre lecture passe d'abord, la sienne ne fait que compléter."""
    scanner = (
        "Article 2 :\nLes références du renouvellement de cette qutorisotion sont :\n"
        'Code RVC -PS,tÂ - GfA / 09.03.3 B/N" 1 JMPH512\nTitulaire :\n'
        "Mention que seul le scanner a lue\n"
    )
    ours = (
        "Article 2 :\nLes références du renouvellement de cette autorisation sont :\n"
        "Code: RVC -PSM- GM / 09.03.3 B/N° 1 JMPHS12\nTitulaire :\n"
    )
    merged = extraction._merge_readings(ours, scanner)

    assert congo_code(fold(merged), merged) == "RVC-PSM-GM/09.03.3 B/N°1 JMPHS12"
    assert "GfA" not in merged  # la ligne déformée ne double pas la bonne
    assert "Mention que seul le scanner a lue" in merged


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


@pytest.mark.skipif(
    not shutil.which("tesseract") or not shutil.os.path.exists(FONT),
    reason="tesseract ou la police d'essai absents de cette machine",
)
def test_a_highlighted_line_is_read(tmp_path):
    """Encre rouge sous surligneur orange : perdue par la lecture simple, lue par la nouvelle."""
    image, draw = page(highlight=True)
    font = ImageFont.truetype(FONT, 34)
    draw.text((60, 60), "Les references de l'autorisation sont :", fill="black", font=font)
    draw.text((70, 188), "RVC-PSM-GM/09.03.3 B/N 9 JMPHS12", fill=(215, 45, 70), font=font)
    draw.text((60, 300), "Titulaire et exploitant", fill="black", font=font)
    path = tmp_path / "page.png"
    image.save(path)

    simple = extraction._tesseract(path, tmp_path / "simple")
    complete = extraction._ocr_image(path, tmp_path, 0)

    assert "JMPHS12" not in simple
    assert "JMPHS12" in complete
    assert "Titulaire" in complete


@pytest.mark.skipif(
    not shutil.which("tesseract")
    or not shutil.which("pdftoppm")
    or not shutil.os.path.exists(FONT),
    reason="tesseract, pdftoppm ou la police d'essai absents de cette machine",
)
def test_a_searchable_pdf_with_a_highlighted_line_is_read_on_the_image(tmp_path):
    """Le PDF porte déjà un texte (celui du scanner, faux sur la ligne surlignée) : la page
    surlignée est quand même lue sur l'image, et le Code en sort juste."""
    from django.core.files import File
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    image, draw = page(highlight=True, size=(1240, 1754))
    font = ImageFont.truetype(FONT, 30)
    draw.text(
        (60, 100), "Les references du renouvellement de cette autorisation", fill="black", font=font
    )
    draw.text((70, 190), "Code: RVC-PSM-GM/09.03.3 B/N 1 JMPHS12", fill=(215, 45, 70), font=font)
    draw.text(
        (60, 300), "sera renouvelee en 2026 a la date butoir du 28 fevrier", fill="black", font=font
    )
    picture = tmp_path / "page.png"
    image.save(picture)
    pdf = tmp_path / "cherchable.pdf"
    sheet = canvas.Canvas(str(pdf), pagesize=(595, 842))
    sheet.drawImage(ImageReader(str(picture)), 0, 0, width=595, height=842)
    layer = sheet.beginText(30, 760)
    layer.setTextRenderMode(3)  # texte invisible, comme celui d'un scanner
    for line in (
        "Les references du renouvellement de cette qutorisotion de mise sur le marche sont",
        'Code RVC -PS,tA - GfA / 09.03.3 B/N" 1 JMPH512',
        "sera renouvelee en 2026 a la date butoir du 28 fevrier",
    ):
        layer.textLine(line)
    sheet.drawText(layer)
    sheet.save()

    with pdf.open("rb") as handle:
        upload = SimpleNamespace(content_type="application/pdf", file=File(handle))
        result = extraction.extract_file(upload)

    text = result["text"]
    assert result["errors"] == []
    assert congo_code(fold(text), text) == "RVC-PSM-GM/09.03.3 B/N°1 JMPHS12"
