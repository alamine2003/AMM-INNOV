"""Dossiers pays (Mali, 25/09/2026) : recueils de décisions, documents communs, pays, dates.

Le dossier « MALI » porte à sa racine des recueils (« AMM groupée 23 DEC 2023 » : six
décisions de deux pages, une par spécialité) et des AMM d'autres produits (PALUCARE). Le
navigateur les joint à chaque produit sous « Documents communs » : seule la décision du produit
doit être lue et rangée, avec ses seules pages.
"""

import hashlib
from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from pypdf import PdfReader, PdfWriter

from apps.catalog.models import Country, Product
from apps.documents.models import Document
from apps.imports.dossier.application import apply_dossier
from apps.imports.dossier.recognition import decision_sections, recognize_file
from apps.imports.models import DossierFile, DossierImport

from .test_dossier_application import ready
from .test_dossier_recognition import staged

pytestmark = pytest.mark.django_db


def mali_decision(specialty: str, number: str = "", day: str = "2 9 DEC 2023") -> str:
    """Une décision malienne telle que lue sur le scan (numéro manuscrit, tampon espacé)."""
    return (
        "MINISTERE DE LA SANTE ET DU DEVELOPPEMENT SOCIAL    REPUBLIQUE DU MALI\n"
        f"DECISION N° {number or '2023'} /MSDS- SG DU\n"
        "PORTANT AUTORISATION DE MISE SUR LE MARCHE DE PRODUITS PHARMACEUTIQUES\n"
        "Vu la Loi n° 2022-001 du 25 février 2022 portant révision de la charte ;\n"
        "Article 1 : L'autorisation de mise sur le marché (AMM) est accordée aux laboratoires :\n"
        "GENERIC HEALTHCARE Private Limited.\n"
        "Pour le débit à titre onéreux ou gratuit de produits pharmaceutiques\n"
        "pour la spécialité :\n"
        f"\n{specialty}\n"
        "\f\n"
        "Article 4 : La durée de validité de l'autorisation de mise sur le marché est de cinq (5) "
        "ans pour compter de la date de signature de la présente décision.\n"
        f"Bamako, le {day}\nLe ministre,\n"
    )


RECUEIL_2023 = "\n\f\n".join(
    [
        mali_decision("GENFER® 100 mg/2 mL, solution injectable, boite de 5 ampoules."),
        mali_decision("DESYREL®, sirop, flacon de 200 mL.", number="2023-003763"),
        mali_decision("LOLIP® 80 mg comprimé pelliculé sécable, boîte de 3x10"),
    ]
)
PALUCARE = mali_decision("PALUCARE 20 mg/160 mg comprimé enrobé, boîte 6", day="1 1 JUIN 2015")


def pdf_bytes(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def stored_pdf(batch, path, text, pages):
    content = pdf_bytes(pages) + path.encode()  # contenu distinct par fichier
    record = DossierFile(
        batch=batch,
        relative_path=path,
        sha256=hashlib.sha256(content).hexdigest(),
        content_type="application/pdf",
        size_bytes=len(content),
        extraction={
            "text": text,
            "source": "pdf_text",
            "confidence": 98,
            "warnings": [],
            "errors": [],
            "page_count": pages,
        },
    )
    record.file.save(path.rsplit("/", 1)[-1], ContentFile(content), save=False)
    record.save()
    return record


@pytest.fixture
def mali(countries):
    return countries["ML"]


@pytest.fixture
def desyrel(ranges, make_amm, mali):
    product = Product.objects.create(name="DESYREL SUSP BUV F/200ML", range=ranges["GENERALE"])
    for other in ("GENFER 100MG/2ML IM AMP INJ B/5", "PALUCARE 20MG/160MG CPR ENR B/6"):
        make_amm(country=mali, product_obj=Product.objects.create(name=other))
    return make_amm(country=mali, product_obj=product, original_number="")


def test_sections_of_a_compilation_follow_its_pages():
    sections = decision_sections(RECUEIL_2023)
    assert [section["specialty"].split()[0] for section in sections] == [
        "GENFER®",
        "DESYREL®,",
        "LOLIP®",
    ]
    assert [(section["first_page"], section["last_page"]) for section in sections] == [
        (1, 2),
        (3, 4),
        (5, 6),
    ]


def test_one_decision_quoting_its_specialty_twice_is_not_a_compilation(users):
    batch = DossierImport.objects.create(root_name="SENEGAL - EXEMPLO", created_by=users["hq"])
    text = (
        "REPUBLIQUE DU SENEGAL\nAnalyse : arrêté portant octroi de l'AMM à la spécialité\n"
        "ARRETE:\nArticle premier.- L'AMM est accordée à la spécialité :\n"
        "EXEMPLO GH 100mg suspension buvable fl/120ml\nSous le numéro : 7897\n"
    )
    row = recognize_file(staged(batch, "SENEGAL - EXEMPLO/AMM.pdf", text), [], [])
    assert row["sections"] == [] and row["number"] == "7897"


def test_country_folder_keeps_only_the_product_pages_and_leaves_other_products_out(users, desyrel):
    batch = DossierImport.objects.create(
        root_name="MALI - DESYREL SUSP BUV F200ML", created_by=users["hq"]
    )
    root = batch.root_name
    stored_pdf(batch, f"{root}/AMM DESYREL.pdf", mali_decision("DESYREL, sirop, flacon"), 2)
    stored_pdf(batch, f"{root}/Documents communs/AMM groupée 23 DEC 2023.pdf", RECUEIL_2023, 6)
    stored_pdf(batch, f"{root}/Documents communs/AMM PALUCARE 20 mg.pdf", PALUCARE, 2)
    preview = ready(batch)
    assert preview["question"] is None, preview["question"]
    assert preview["amm"]["id"] == str(desyrel.pk)
    assert [item["path"].rsplit("/", 1)[-1] for item in preview["ignored"]] == [
        "AMM PALUCARE 20 mg.pdf"
    ]
    recueil = next(doc for doc in preview["documents"] if "groupée" in doc["path"])
    assert recueil["pages"] == [3, 4] and recueil["official"]
    # Le numéro et la date viennent de la décision du produit, pas du reste du recueil.
    assert preview["original"]["original_number"] == "2023-003763"
    assert preview["original"]["original_start_date"] is None or preview["original"][
        "original_start_date"
    ].startswith("2023-12")

    apply_dossier(batch.pk, user=users["hq"], token=batch.preview_token)
    titles = sorted(Document.objects.filter(amm=desyrel).values_list("title", flat=True))
    assert titles == ["AMM DESYREL.pdf", "AMM groupée 23 DEC 2023.pdf (p. 3-4)"]
    extract = Document.objects.get(amm=desyrel, title__endswith="(p. 3-4)")
    with extract.file.open("rb") as stream:
        assert len(PdfReader(BytesIO(stream.read())).pages) == 2
    assert not Document.objects.filter(title__startswith="AMM PALUCARE").exists()


def test_unit_abbreviations_in_names_are_not_countries(users, countries):
    """« Mali Maglife 100 mg cp » : « mg » n'est pas Madagascar (question « plusieurs pays »)."""
    Country.objects.create(iso2="MG", name="Madagascar")
    Country.objects.create(iso2="NE", name="Niger")
    batch = DossierImport.objects.create(
        root_name="MALI - MAGLIFE 100MG CPR B60", created_by=users["hq"]
    )
    upload = staged(
        batch,
        f"{batch.root_name}/Avis favorable Mali Maglife 100 mg cp.pdf",
        "Le ministre ne peut pas signer : 100 mg, 5 ml.",
    )
    row = recognize_file(upload, list(Country.objects.all()), [], batch.root_name)
    assert row["country_ids"] == [str(countries["ML"].pk)]


def test_provisional_notification_is_an_annex(users):
    batch = DossierImport.objects.create(root_name="MALI - MAGLIFE", created_by=users["hq"])
    text = (
        "REPUBLIQUE DU MALI\nObjet : notification provisoire d'Autorisation de Mise sur le "
        "Marché (AMM).\nLes décisions ministérielles portant AMM vous parviendront ultérieurement."
    )
    upload = staged(batch, f"{batch.root_name}/Avis favorable Mali Maglife.pdf", text)
    row = recognize_file(upload, [], [])
    assert not row["official"] and row["kind"] == "AUTRE"


def test_mali_notification_takes_the_ministerial_decision_number_and_date(users):
    batch = DossierImport.objects.create(root_name="MALI - CEFIXIM", created_by=users["hq"])
    text = (
        "REPUBLIQUE DU MALI\nObjet : notification d'Autorisation de Mise sur le Marché\n"
        "la présente que l'Autorisation de Mise sur le Marché pour la spécialité :\n"
        "CEFIXIM GH 200 mg comprimé, boîte de 8.\n"
        "Sous le N° 24 — 000829 du 25 juin 2024 suivant Décision ministérielle N° "
        "2024-0000675/MSDS-SG du 15\navril 2024,\n"
    )
    row = recognize_file(staged(batch, "MALI - CEFIXIM/AMM.pdf", text), [], [])
    assert row["number"] == "2024-0000675"
    assert row["start_date"] == "2024-04-15"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Bamako, le 2 9 DEC 2023", "2023-12-29"),
        ("COTONOU, le2 6 JUIN 2019", "2019-06-26"),
        ("CORONOU, le 16 avr 2019", "2019-04-16"),  # ville mal lue
        ("Ministère de la Santé 15.04. 2026*00 9037", "2026-04-15"),  # tampon sénégalais
        ("Bamako, le 2 1 OCT 2071", None),  # tampon mal lu : date future écartée
    ],
)
def test_signature_dates_read_from_stamps(users, line, expected):
    batch = DossierImport.objects.create(root_name="DOSSIER", created_by=users["hq"])
    text = f"REPUBLIQUE\nDECISION portant autorisation de mise sur le marché\n{line}\n"
    row = recognize_file(staged(batch, "DOSSIER/AMM.pdf", text), [], [])
    assert row["decision_date"] == expected


def test_reprise_archives_common_documents_filed_in_unrelated_records(users, desyrel):
    """Rangés avant le 26/09/2026 dans la fiche de DESYREL : PALUCARE est archivé, le recueil
    qui contient la décision de DESYREL reste en place."""
    from apps.imports.dossier.cleanup import detach_unrelated_common_documents
    from apps.imports.models import DossierReviewPoint

    batch = DossierImport.objects.create(
        root_name="MALI - DESYREL SUSP BUV F200ML",
        created_by=users["hq"],
        status=DossierImport.Status.APPLIED,
        amm=desyrel,
    )
    root = batch.root_name
    kept, dropped = [], []
    for path, text, bucket in (
        (f"{root}/Documents communs/AMM groupée 23 DEC 2023.pdf", RECUEIL_2023, kept),
        (f"{root}/Documents communs/AMM PALUCARE 20 mg.pdf", PALUCARE, dropped),
    ):
        source = stored_pdf(batch, path, text, 2)
        source.document = Document.objects.create(
            amm=desyrel,
            title=path.rsplit("/", 1)[-1],
            document_date="2023-12-29",
            file=f"documents/{source.sha256}.pdf",
            sha256=source.sha256,
        )
        source.save()
        bucket.append(source.document)
    DossierReviewPoint.objects.create(
        batch=batch,
        amm=desyrel,
        code="identity",
        message="décision groupée où « DESYREL » n'a pas été trouvé",
        proof_file=DossierFile.objects.get(document=dropped[0]),
        fingerprint="x",
    )

    assert detach_unrelated_common_documents(dry_run=True)["archived"] == 1
    assert not Document.objects.filter(archived_at__isnull=False).exists()
    report = detach_unrelated_common_documents()
    assert report["archived"] == 1 and report["kept"] == 1 and report["points_closed"] == 1
    dropped[0].refresh_from_db()
    kept[0].refresh_from_db()
    assert dropped[0].archived_at is not None and kept[0].archived_at is None
    assert detach_unrelated_common_documents()["examined"] == 1  # idempotente


def test_ivory_coast_name_above_the_visa_line():
    from apps.imports.dossier.matching import pick_table_row
    from apps.imports.dossier.recognition import table_rows

    text = (
        "Dénomination N° de visa| Date de DCI Conditions | PFHT\n"
        "AMLO VH 5 mg/12,5 mg/160 mg Amlodipine,\n"
        "comprimés pelliculés E-2015- 418 | 29/07/2015 |Hydrochlorothiazide, Liste I 7.871,5\n"
        "boite de 30 Valsartan\n"
        "AMLO VH 10 mg/25 mg/160 mg Amlodipine,\n"
        "comprimés pelliculés E-2015-421 | 29/07/2015 |Hydrochlorothiazide, Liste I 7.871,5\n"
        "BONCIPRO 500 mg comprimés . . .\n"
        "boite de 20 E-2013-756 | 19-12-2013 | Ciprofloxacine Liste I 2.295,8\n"
    )
    rows = table_rows(text)
    product = Product.objects.create(name="AMLO VH 10MG/25MG/160MG CPR B/30")
    others = [Product.objects.create(name="AMLO VH 5MG/12,5MG/160MG CPR B/30"), product]
    line = pick_table_row(rows, product, others)
    assert line["number"] == "E-2015-421" and line["date"] == "2015-07-29"


def test_same_number_with_leading_zeros_is_not_a_discrepancy():
    from apps.imports.dossier.preview import _change

    assert _change("amm", "original_number", "E-2015-0418", "E-2015- 418", "f", 90) is None
    assert _change("amm", "original_number", "E-2015-0418", "E-2015-0419", "f", 90)

