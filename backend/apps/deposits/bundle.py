"""Le dossier complet que le pays télécharge : un ZIP rangé comme le dossier papier.

00 - Bordereau.pdf                  (pièces, échantillons, consignes)
01 - Lettre de demande de renouvellement/…
02 - Certificat de PGHT/…
…
Autres pièces/…
"""

import io
import re

from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .actions import piece_types_for
from .models import DepositDossier


def _safe(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", text).strip()[:80] or "Pièce"


def _checklist(dossier: DepositDossier):
    pieces = list(dossier.pieces.select_related("piece_type"))
    types = piece_types_for(dossier.renewal.amm.country)
    rows = [
        (
            piece_type.label,
            piece_type.required,
            [piece for piece in pieces if piece.piece_type_id == piece_type.pk],
        )
        for piece_type in types
    ]
    known = {piece_type.pk for piece_type in types}
    others = [piece for piece in pieces if piece.piece_type_id not in known]
    return rows, others


def bordereau(dossier: DepositDossier) -> bytes:
    amm = dossier.renewal.amm
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Dossier de renouvellement {amm.product.name}",
    )
    rows, others = _checklist(dossier)
    story = [
        Paragraph("Dossier de renouvellement d'AMM", styles["Title"]),
        Paragraph(f"<b>{amm.product.name}</b> — {amm.country.name}", styles["Heading2"]),
        Paragraph(
            f"AMM n° {amm.original_number or '—'} · renouvellement n°{dossier.renewal.sequence}"
            + (f" · échéance {amm.effective_end_date:%d/%m/%Y}" if amm.effective_end_date else ""),
            styles["Normal"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Pièces du dossier", styles["Heading3"]),
    ]
    table = [["", "Pièce", "Fichiers"]]
    for index, (label, required, files) in enumerate(rows, start=1):
        table.append(
            [
                f"{index:02d}",
                label + ("" if required else " (facultative)"),
                "\n".join(piece.filename for piece in files) or "—",
            ]
        )
    for piece in others:
        table.append(["+", piece.label, piece.filename])
    grid = Table(table, colWidths=[12 * mm, 70 * mm, 92 * mm], repeatRows=1)
    grid.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3eaf5")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa8bd")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story += [grid, Spacer(1, 6 * mm), Paragraph("Échantillons", styles["Heading3"])]
    samples = list(dossier.samples.all())
    if samples:
        sample_rows = [["N° de lot", "Fabrication", "Péremption", "Quantité"]] + [
            [
                sample.batch_number,
                f"{sample.manufactured_on:%d/%m/%Y}",
                f"{sample.expires_on:%d/%m/%Y}",
                str(sample.quantity or "—"),
            ]
            for sample in samples
        ]
        sample_grid = Table(sample_rows, colWidths=[50 * mm, 40 * mm, 40 * mm, 44 * mm])
        sample_grid.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3eaf5")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa8bd")),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(sample_grid)
    else:
        story.append(Paragraph("Pas d'échantillons pour ce dépôt.", styles["Normal"]))
    story += [
        Spacer(1, 6 * mm),
        Paragraph("À faire par le pays", styles["Heading3"]),
        Paragraph(
            "1. Déposer le dossier et les échantillons à l'agence de régulation.<br/>"
            "2. Dans AMM GH, rubrique « Dépôts AMM », enregistrer la date de dépôt et envoyer "
            "l'attestation de dépôt au siège.<br/>"
            "3. Noter ensuite chaque passage en commission et chaque notification de l'agence.",
            styles["Normal"],
        ),
    ]
    if dossier.send_note:
        story += [
            Spacer(1, 4 * mm),
            Paragraph("Message du siège", styles["Heading3"]),
            Paragraph(dossier.send_note.replace("\n", "<br/>"), styles["Normal"]),
        ]
    story += [
        Spacer(1, 8 * mm),
        Paragraph(
            f"Préparé le {timezone.localtime():%d/%m/%Y à %H:%M}"
            + (f", envoyé par {dossier.sent_by.full_name}" if dossier.sent_by else ""),
            styles["Italic"],
        ),
    ]
    document.build(story)
    return buffer.getvalue()


def entries(dossier: DepositDossier):
    """`(nom dans le ZIP, fichier)`, bordereau en tête, pièces dans l'ordre de la liste."""
    rows, others = _checklist(dossier)
    sheet = ContentFile(bordereau(dossier), name="bordereau.pdf")
    yield "00 - Bordereau du dossier.pdf", sheet
    used: set[str] = set()
    for index, (label, _required, files) in enumerate(rows, start=1):
        for piece in files:
            yield _unique(f"{index:02d} - {_safe(label)}/{_safe(piece.filename)}", used), piece.file
    for piece in others:
        yield _unique(f"Autres pièces/{_safe(piece.filename)}", used), piece.file


def _unique(name: str, used: set[str]) -> str:
    candidate, number = name, 1
    while candidate in used:
        number += 1
        stem, _, ext = name.rpartition(".")
        candidate = f"{stem} ({number}).{ext}" if stem else f"{name} ({number})"
    used.add(candidate)
    return candidate


def zip_name(dossier: DepositDossier) -> str:
    amm = dossier.renewal.amm
    return f"Depot_{amm.country.iso2}_{_safe(amm.product.name).replace(' ', '_')}.zip"
