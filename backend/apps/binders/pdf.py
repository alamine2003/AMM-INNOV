"""Le classeur en PDF, page par page, comme à l'écran : couverture, intercalaires de couleur,
une feuille perforée par AMM, puis le bilan (dossiers à retrouver, à scanner, pages en trop).

Une page pas encore vérifiée porte un cadre de constat à cocher à la main : le PDF imprimé sert
aussi de feuille de route pour vérifier le classeur papier.
"""

from datetime import date, datetime
from io import BytesIO

from django.utils import timezone
from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

from apps.core.dates import today

WIDTH, HEIGHT = A4
PAPER = HexColor("#fbf8f1")
INK = HexColor("#1d2433")
MUTED = HexColor("#6b7280")
LINE = HexColor("#d8d2c4")
NAVY = HexColor("#16213d")
HIGHLIGHT = HexColor("#fff3b0")
LEFT = 64  # après les perforations
RIGHT = WIDTH - 44  # avant les onglets
FIELD_LABELS = {"number": "N° d'AMM", "start_date": "Date de début", "end_date": "Date de fin"}
SLOT_LABELS = {"original": "origine", "renewal": "renouvellement"}
STAMPS = {
    "CONFORME": ("VÉRIFIÉ", HexColor("#2e7d32")),
    "CORRIGE": ("CORRIGÉ", HexColor("#e65100")),
    "ABSENT": ("ABSENT", HexColor("#c62828")),
}
STATUS_COLORS = {
    "VALIDE": HexColor("#2e7d32"),
    "A_RENOUVELER": HexColor("#e65100"),
    "EXPIRE": HexColor("#c62828"),
    "INDETERMINE": MUTED,
}


def _tint(color: Color, amount: float) -> Color:
    """Mélange avec du blanc (amount = part de blanc)."""
    return Color(
        color.red + (1 - color.red) * amount,
        color.green + (1 - color.green) * amount,
        color.blue + (1 - color.blue) * amount,
    )


def _date(value) -> str:
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, str) and len(value) == 10 and value[4] == "-":
        return f"{value[8:10]}/{value[5:7]}/{value[:4]}"
    return value or "—"


def _value(field: str, value) -> str:
    return _date(value) if field != "number" else (value or "—")


class BinderDocument:
    def __init__(self, binder: dict, generated_by: str, attachments: dict | None = None):
        """`attachments` (amm_id → nombre de décisions jointes) : version avec les décisions
        officielles, où chaque fiche est suivie de ses scans (voir `export`)."""
        self.binder = binder
        self.generated_by = generated_by
        self.attachments = attachments
        # Index (0 = première page) de la fiche de chaque AMM dans le PDF produit.
        self.page_index: dict[str, int] = {}
        self.buffer = BytesIO()
        self.canvas = Canvas(self.buffer, pagesize=A4)
        self.canvas.setTitle(f"Classeur {binder['country_name']} — {binder['title']}")
        self.canvas.setAuthor("AMM GH")
        self.sections = binder["sections"]
        self.total = sum(section["total"] for section in self.sections)

    # --- Éléments communs -------------------------------------------------------------------

    def _paper(self, fill=PAPER):
        c = self.canvas
        c.setFillColor(fill)
        c.rect(0, 0, WIDTH, HEIGHT, stroke=0, fill=1)

    def _holes(self):
        """Deux perforations renforcées, comme une feuille de classeur à levier."""
        c = self.canvas
        for y in (HEIGHT * 0.32, HEIGHT * 0.68):
            c.setStrokeColor(HexColor("#cfc7b5"))
            c.setLineWidth(2.2)
            c.setFillColor(HexColor("#efe9dc"))
            c.circle(30, y, 12.5, stroke=1, fill=1)
            c.setFillColor(HexColor("#b9b2a3"))
            c.circle(30, y, 8, stroke=0, fill=1)
            c.setFillColor(HexColor("#8f887a"))
            c.circle(30.8, y + 0.8, 6.4, stroke=0, fill=1)

    def _tab(self, index: int, label: str, color: Color, width: float = 26):
        """Onglet d'intercalaire sur la tranche, décalé selon la gamme."""
        c = self.canvas
        top = HEIGHT - 110 - index * 118
        c.setFillColor(color)
        c.roundRect(WIDTH - width, top - 100, width + 8, 100, 6, stroke=0, fill=1)
        c.saveState()
        c.translate(WIDTH - width / 2 + 3.5, top - 50)
        c.rotate(-90)
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 9.5)
        c.drawCentredString(0, 0, label.upper())
        c.restoreState()

    def _section_index(self, code: str) -> int:
        for index, section in enumerate(self.sections):
            if section["code"] == code:
                return index
        return 0

    def _footer(self):
        c = self.canvas
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawString(
            LEFT,
            24,
            f"AMM GH · Classeur {self.binder['country_name']} — {self.binder['title']} · "
            f"généré le {today():%d/%m/%Y} par {self.generated_by}",
        )

    def _pill(self, x, y, text, color, size=8.5):
        c = self.canvas
        c.setFont("Helvetica-Bold", size)
        width = c.stringWidth(text, "Helvetica-Bold", size) + 14
        c.setFillColor(color)
        c.roundRect(x, y - 4, width, size + 8, (size + 8) / 2, stroke=0, fill=1)
        c.setFillColor(white)
        c.drawString(x + 7, y + 0.5, text)
        return width

    # --- Couverture ---------------------------------------------------------------------------

    def cover(self):
        c = self.canvas
        b = self.binder
        self._paper(NAVY)
        # Grain de la couverture : fines rayures.
        c.setStrokeColor(Color(1, 1, 1, alpha=0.035))
        c.setLineWidth(0.6)
        for x in range(0, int(WIDTH), 6):
            c.line(x, 0, x, HEIGHT)
        # Étiquette de dos collée sur la couverture.
        c.setFillColor(HexColor("#f4efe3"))
        c.roundRect(110, HEIGHT - 430, WIDTH - 220, 260, 10, stroke=0, fill=1)
        c.setStrokeColor(HexColor("#c9bfa8"))
        c.setLineWidth(1)
        c.roundRect(118, HEIGHT - 422, WIDTH - 236, 244, 7, stroke=1, fill=0)
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(
            WIDTH / 2,
            HEIGHT - 212,
            "AMM GH · CLASSEUR AVEC DÉCISIONS OFFICIELLES"
            if self.attachments is not None
            else "AMM GH · CLASSEUR DES AMM",
        )
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(WIDTH / 2, HEIGHT - 268, b["country_name"].upper())
        c.setFont("Helvetica", 18)
        c.drawCentredString(WIDTH / 2, HEIGHT - 300, b["title"])
        x = (
            WIDTH / 2
            - sum(c.stringWidth(s["label"], "Helvetica-Bold", 9) + 20 for s in self.sections) / 2
        )
        for section in self.sections:
            x += self._pill(x, HEIGHT - 340, section["label"], HexColor(section["color"]), 9) + 6
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 10)
        c.drawCentredString(
            WIDTH / 2,
            HEIGHT - 395,
            f"{self.total} pages · {b['checked']} vérifiées · état au {today():%d/%m/%Y}",
        )
        # Chiffres clés.
        tiles = [
            ("Pages", b["total"]),
            ("Vérifiées", b["checked"]),
            ("Corrigées", b["corrected"]),
            ("Absentes", b["absent"]),
            ("À scanner", b["to_scan"]),
            ("En trop", b["extras"]),
        ]
        tile_w = (WIDTH - 160) / 3
        for i, (label, value) in enumerate(tiles):
            tx = 80 + (i % 3) * tile_w
            ty = 250 - (i // 3) * 78
            c.setFillColor(Color(1, 1, 1, alpha=0.08))
            c.roundRect(tx + 6, ty, tile_w - 12, 62, 8, stroke=0, fill=1)
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 22)
            c.drawString(tx + 20, ty + 30, str(value))
            c.setFont("Helvetica", 9)
            c.setFillColor(HexColor("#c7cfe0"))
            c.drawString(tx + 20, ty + 14, label)
        progress = b["checked"] / b["total"] if b["total"] else 0
        c.setFillColor(Color(1, 1, 1, alpha=0.15))
        c.roundRect(86, 120, WIDTH - 172, 8, 4, stroke=0, fill=1)
        c.setFillColor(HexColor("#4caf50"))
        if progress:
            c.roundRect(86, 120, max((WIDTH - 172) * progress, 8), 8, 4, stroke=0, fill=1)
        c.setFillColor(HexColor("#c7cfe0"))
        c.setFont("Helvetica", 8)
        c.drawCentredString(WIDTH / 2, 100, f"Généré le {today():%d/%m/%Y} par {self.generated_by}")
        c.showPage()

    # --- Intercalaire -------------------------------------------------------------------------

    def divider(self, section: dict):
        c = self.canvas
        color = HexColor(section["color"])
        self._paper(_tint(color, 0.72))
        self._holes()
        self._tab(self._section_index(section["code"]), section["label"], color, width=40)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 54)
        c.drawCentredString(WIDTH / 2 - 10, HEIGHT / 2 + 40, section["label"].upper())
        c.setFillColor(INK)
        c.setFont("Helvetica", 14)
        c.drawCentredString(
            WIDTH / 2 - 10,
            HEIGHT / 2,
            f"{section['total']} pages · {section['checked']} vérifiées",
        )
        bar = 260
        x = WIDTH / 2 - 10 - bar / 2
        c.setFillColor(Color(1, 1, 1, alpha=0.7))
        c.roundRect(x, HEIGHT / 2 - 30, bar, 8, 4, stroke=0, fill=1)
        if section["total"] and section["checked"]:
            c.setFillColor(color)
            c.roundRect(
                x,
                HEIGHT / 2 - 30,
                max(bar * section["checked"] / section["total"], 8),
                8,
                4,
                stroke=0,
                fill=1,
            )
        if section["pages"]:
            first, last = section["pages"][0], section["pages"][-1]
            c.setFont("Helvetica", 10)
            c.setFillColor(MUTED)
            c.drawCentredString(
                WIDTH / 2 - 10,
                HEIGHT / 2 - 60,
                f"de {first['product_name'][:40]} à {last['product_name'][:40]}",
            )
        self._footer()
        c.showPage()

    # --- Page d'une AMM -----------------------------------------------------------------------

    def _slot_card(self, x, y, width, title, slot, values, discrepancies):
        """Bloc « AMM d'origine » ou « Dernier renouvellement » ; renvoie la hauteur."""
        c = self.canvas
        height = 132
        c.setFillColor(white)
        c.setStrokeColor(LINE)
        c.setLineWidth(0.8)
        c.roundRect(x, y - height, width, height, 8, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(x + 14, y - 20, title.upper())
        if values is None:
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(x + 14, y - 52, "Aucun renouvellement enregistré")
            return height
        gaps = {d["field"]: d for d in discrepancies if d["slot"] == slot}
        row_y = y - 46
        for field in ("number", "start_date", "end_date"):
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 8.5)
            c.drawString(x + 14, row_y, FIELD_LABELS[field])
            text = _value(field, values[field])
            c.setFont("Helvetica-Bold", 11.5)
            text_w = c.stringWidth(text, "Helvetica-Bold", 11.5)
            if field in gaps:
                c.setFillColor(HIGHLIGHT)
                c.rect(x + 104, row_y - 4, min(text_w + 8, width - 116), 16, stroke=0, fill=1)
            c.setFillColor(INK)
            c.drawString(x + 108, row_y, text[:30])
            if field in gaps:
                c.setFillColor(HexColor("#b45309"))
                c.setFont("Helvetica", 7.5)
                c.drawString(
                    x + 108, row_y - 12, f"le scan indique {_value(field, gaps[field]['scan'])}"
                )
            c.setStrokeColor(LINE)
            c.setDash(1, 2)
            c.line(x + 14, row_y - 17, x + width - 14, row_y - 17)
            c.setDash()
            row_y -= 30
        return height

    def _stamp(self, check: dict, x: float, y: float):
        c = self.canvas
        label, color = STAMPS[check["result"]]
        c.saveState()
        c.translate(x, y)
        c.rotate(12)
        c.setStrokeColor(color)
        c.setFillColor(Color(color.red, color.green, color.blue, alpha=0.06))
        c.setLineWidth(2.6)
        c.roundRect(-78, -32, 156, 64, 8, stroke=1, fill=1)
        c.setLineWidth(0.9)
        c.roundRect(-72, -26, 144, 52, 5, stroke=1, fill=0)
        c.setFillColor(color)
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(0, 2, label)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(
            0, -16, f"{_date(check['checked_at'])} · {(check['checked_by'] or '')[:24]}"
        )
        c.restoreState()

    def _checkbox_form(self, y: float):
        """Cadre de constat vierge, à remplir à la main sur le classeur papier."""
        c = self.canvas
        c.setStrokeColor(LINE)
        c.setFillColor(white)
        c.roundRect(LEFT, y - 110, RIGHT - LEFT, 110, 8, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(LEFT + 14, y - 20, "CONSTAT DE L'ARCHIVISTE")
        x = LEFT + 14
        c.setFont("Helvetica", 10)
        c.setFillColor(INK)
        for label in ("Conforme", "Corrigé", "Absent du classeur", "À scanner"):
            c.setStrokeColor(INK)
            c.rect(x, y - 46, 10, 10, stroke=1, fill=0)
            c.drawString(x + 15, y - 45, label)
            x += c.stringWidth(label, "Helvetica", 10) + 42
        c.setStrokeColor(LINE)
        c.setDash(1, 2)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(LEFT + 14, y - 72, "Observations")
        c.line(LEFT + 80, y - 73, RIGHT - 14, y - 73)
        c.drawString(LEFT + 14, y - 96, "Nom et date")
        c.line(LEFT + 80, y - 97, RIGHT - 14, y - 97)
        c.setDash()

    def page(self, page: dict, section: dict):
        c = self.canvas
        self.page_index[page["amm_id"]] = c.getPageNumber() - 1
        color = HexColor(section["color"])
        self._paper()
        self._holes()
        self._tab(self._section_index(section["code"]), section["label"], color)
        b = self.binder
        # En-tête.
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(
            LEFT, HEIGHT - 50, f"{b['country_name'].upper()} · CLASSEUR {b['title'].upper()}"
        )
        c.drawRightString(RIGHT, HEIGHT - 50, f"PAGE {page['page']} / {self.total}")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 21)
        lines = simpleSplit(page["product_name"], "Helvetica-Bold", 21, RIGHT - LEFT)[:2]
        y = HEIGHT - 84
        for line in lines:
            c.drawString(LEFT, y, line)
            y -= 25
        width = self._pill(LEFT, y - 2, section["label"], color)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(
            LEFT + width + 10,
            y + 1,
            f"page {page['section_page']} / {section['total']} de la gamme",
        )
        y -= 20
        c.setStrokeColor(LINE)
        c.setLineWidth(1)
        c.line(LEFT, y, RIGHT, y)
        y -= 18
        # AMM d'origine et dernier renouvellement.
        gap = 14
        card_w = (RIGHT - LEFT - gap) / 2
        height = self._slot_card(
            LEFT, y, card_w, "AMM d'origine", "original", page["original"], page["discrepancies"]
        )
        self._slot_card(
            LEFT + card_w + gap,
            y,
            card_w,
            "Dernier renouvellement",
            "renewal",
            page["renewal"],
            page["discrepancies"],
        )
        y -= height + 16
        # Situation.
        c.setFillColor(white)
        c.setStrokeColor(LINE)
        c.roundRect(LEFT, y - 84, RIGHT - LEFT, 84, 8, stroke=1, fill=1)
        c.setFillColor(MUTED)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(LEFT + 14, y - 20, "SITUATION")
        c.setFont("Helvetica", 8.5)
        c.drawString(LEFT + 14, y - 42, "Statut")
        c.drawString(LEFT + 14, y - 64, "Scan de la décision")
        self._pill(
            LEFT + 120,
            y - 43,
            page["status_label"],
            STATUS_COLORS.get(page["status"], MUTED),
            8,
        )
        dossier = "Dossier complet" if page["dossier_state"] == "COMPLET" else "Dossier incomplet"
        c.setFillColor(INK)
        c.setFont("Helvetica", 9.5)
        c.drawString(LEFT + 260, y - 42, dossier)
        scan = page["scan"]
        if scan:
            pages = f" · {scan['page_count']} p." if scan.get("page_count") else ""
            text = f"Scan du {_date(scan['document_date'])}{pages}"
        else:
            text = "Aucun scan dans AMM GH"
        c.setFont("Helvetica-Bold" if not scan else "Helvetica", 9.5)
        c.setFillColor(INK if scan else HexColor("#c62828"))
        c.drawString(LEFT + 120, y - 64, text)
        if page["to_scan"]:
            self._pill(LEFT + 260, y - 65, "À SCANNER", HexColor("#c62828"), 8)
        filed = page.get("pending_renewal")
        if filed:
            label = "DÉPOSÉ" if filed["workflow_status"] == "DEPOSE" else "EN INSTRUCTION"
            when = f" LE {_date(filed['filing_date'])}" if filed.get("filing_date") else ""
            self._pill(LEFT + 360, y - 43, f"{label}{when}", HexColor("#1565c0"), 7.5)
        joined = (self.attachments or {}).get(page["amm_id"], 0)
        if joined:
            self._pill(
                RIGHT - 150,
                y - 20,
                f"{joined} DÉCISION{'S' if joined > 1 else ''} JOINTE{'S' if joined > 1 else ''} ›",
                NAVY,
                7.5,
            )
        y -= 84 + 16
        # Écarts relevés à la lecture du scan.
        if page["discrepancies"]:
            messages = [d["message"] for d in page["discrepancies"]][:4]
            wrapped = [
                line
                for message in messages
                for line in simpleSplit(f"• {message}", "Helvetica", 8.5, RIGHT - LEFT - 28)
            ][:8]
            box = 30 + 12 * len(wrapped)
            c.setFillColor(HexColor("#fff8e1"))
            c.setStrokeColor(HexColor("#f0c36d"))
            c.roundRect(LEFT, y - box, RIGHT - LEFT, box, 8, stroke=1, fill=1)
            c.setFillColor(HexColor("#8a5a00"))
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(
                LEFT + 14, y - 18, "ÉCARTS ENTRE LA FICHE ET LE SCAN — À TRANCHER SUR LE PAPIER"
            )
            c.setFont("Helvetica", 8.5)
            for i, line in enumerate(wrapped):
                c.drawString(LEFT + 14, y - 32 - 12 * i, line)
            y -= box + 16
        # Constat.
        check = page["check"]
        if check:
            if check["corrections"]:
                c.setFillColor(MUTED)
                c.setFont("Helvetica-Bold", 8.5)
                c.drawString(LEFT, y - 12, "CORRECTIONS LUES SUR LE PAPIER")
                c.setFont("Helvetica", 9)
                c.setFillColor(INK)
                for i, fix in enumerate(check["corrections"][:6]):
                    c.drawString(
                        LEFT,
                        y - 28 - 13 * i,
                        f"{FIELD_LABELS[fix['field']]} ({SLOT_LABELS[fix['slot']]}) : "
                        f"{_value(fix['field'], fix['old'])} remplacé par "
                        f"{_value(fix['field'], fix['new'])}",
                    )
            if check["note"]:
                c.setFillColor(MUTED)
                c.setFont("Helvetica-Oblique", 9)
                for i, line in enumerate(
                    simpleSplit(f"Note : {check['note']}", "Helvetica-Oblique", 9, 300)[:4]
                ):
                    c.drawString(LEFT, 170 - 12 * i, line)
            self._stamp(check, RIGHT - 100, 110)
        else:
            self._checkbox_form(max(min(y, 250), 160))
        self._footer()
        c.showPage()

    # --- Bilan --------------------------------------------------------------------------------

    def report(self):
        c = self.canvas
        state = {"y": 0}

        def new_page():
            self._paper()
            self._holes()
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold", 20)
            c.drawString(LEFT, HEIGHT - 64, "Bilan du classeur")
            c.setFont("Helvetica", 10)
            c.setFillColor(MUTED)
            c.drawString(
                LEFT, HEIGHT - 82, f"{self.binder['country_name']} — {self.binder['title']}"
            )
            state["y"] = HEIGHT - 116

        def line(text, font="Helvetica", size=9.5, color=INK, indent=0, space=14):
            if state["y"] < 60:
                self._footer()
                c.showPage()
                new_page()
            c.setFont(font, size)
            c.setFillColor(color)
            c.drawString(LEFT + indent, state["y"], text[:110])
            state["y"] -= space

        new_page()
        b = self.binder
        line(
            f"{b['total']} pages · {b['checked']} vérifiées · {b['conformes']} conformes · "
            f"{b['corrected']} corrigées · {b['absent']} absentes · {b['to_scan']} à scanner · "
            f"{b['extras']} en trop",
            space=26,
        )
        pages = [page for section in self.sections for page in section["pages"]]
        groups = [
            (
                "Dossiers à retrouver (absents du classeur)",
                [p for p in pages if p["check"] and p["check"]["result"] == "ABSENT"],
            ),
            (
                "Décisions à scanner (papier présent, pas de scan)",
                [p for p in pages if p["to_scan"]],
            ),
            ("Pages corrigées", [p for p in pages if p["check"] and p["check"]["corrections"]]),
            ("Pages pas encore vérifiées", [p for p in pages if not p["check"]]),
        ]
        for title, items in groups:
            line(f"{title} ({len(items)})", font="Helvetica-Bold", size=11, space=16)
            for item in items:
                line(f"p. {item['page']}  {item['product_name']}", indent=12)
            state["y"] -= 10
        line(
            f"Pages en trop : dossiers sans AMM dans AMM GH ({len(b['extra_pages'])})",
            font="Helvetica-Bold",
            size=11,
            space=16,
        )
        for extra in b["extra_pages"]:
            note = f" — {extra['note']}" if extra["note"] else ""
            line(f"{extra['product_name']}{note}", indent=12)
        self._footer()
        c.showPage()

    def build(self) -> bytes:
        self.cover()
        for section in self.sections:
            self.divider(section)
            for page in section["pages"]:
                self.page(page, section)
        self.report()
        self.canvas.save()
        return self.buffer.getvalue()


def binder_pdf(binder: dict, *, generated_by: str) -> bytes:
    return BinderDocument(binder, generated_by).build()
