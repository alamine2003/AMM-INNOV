"""Relit les décisions du Congo déjà rangées : Code de l'article 2, périodes au 28 février."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.binders import relecture as congo

READINGS = {
    "code": "Code lu",
    "code-illisible": "CODE ILLISIBLE : à relever sur le papier",
    "illisible": "SCAN ILLISIBLE",
    "ancien-modele": "ancien modèle, numéro gardé",
    "sans-scan": "sans scan, dates seulement",
}
FIELDS = {"number": "n°", "start_date": "début", "end_date": "fin"}
SOURCES = {"ocr": ", lu sur l'image", "pdf_text": ", texte du PDF"}


class Command(BaseCommand):
    help = (
        "Sans option : relit chaque décision du Congo et écrit ce qui changerait dans "
        "--rapport (rien n'est modifié). Avec --appliquer : écrit les propositions du rapport, "
        "sauf sur les pages déjà vérifiées (--avec-verifiees pour les inclure)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--rapport", default="/tmp/relecture-congo.json")
        parser.add_argument("--appliquer", action="store_true")
        parser.add_argument("--avec-verifiees", action="store_true")
        parser.add_argument(
            "--pages", default="", help="pages du classeur à relire, par exemple 1-20 ou 113"
        )

    def handle(self, *args, rapport, appliquer, avec_verifiees, pages, **options):
        path = Path(rapport)
        if appliquer:
            if not path.exists():
                raise CommandError(f"Rapport introuvable : {path} (lancer d'abord la relecture)")
            proposals = json.loads(path.read_text(encoding="utf-8"))
            report = congo.apply(proposals, include_verified=avec_verifiees)
            self.stdout.write(
                f"{report['amms']} fiches corrigées ({report['fields']} valeurs), "
                f"{report['skipped_verified']} pages vérifiées laissées, "
                f"{report['stale']} valeurs changées entre-temps laissées, "
                f"{len(report['errors'])} erreurs"
            )
            for error in report["errors"]:
                self.stdout.write(f"  ERREUR {error}")
            return

        def progress(index, product, verified, periods):
            mark = " [vérifiée]" if verified else ""
            self.stdout.write(f"page {index:3d}. {product}{mark}")
            for period in periods:
                where = "origine" if period["slot"] == "original" else "renouvellement"
                source = SOURCES.get(period["source"], "")
                changes = " ; ".join(
                    f"{FIELDS[c['field']]} {c['old'] or '—'} → {c['new']}"
                    for c in period["changes"]
                )
                self.stdout.write(
                    f"          {where} ({READINGS[period['reading']]}{source}) : "
                    f"{changes or 'inchangé'}"
                )
            self.stdout.flush()

        span = None
        if pages:
            first, _, last = pages.partition("-")
            try:
                span = (int(first), int(last or first))
            except ValueError as exc:
                raise CommandError("--pages attend « 1-20 » ou « 113 »") from exc
        proposals = congo.propose(pages=span, progress=progress)
        path.write_text(json.dumps(proposals, ensure_ascii=False, indent=1), encoding="utf-8")
        verified = sum(1 for p in proposals if p["verified"])
        unreadable = sum(
            1
            for p in proposals
            for period in p["periods"]
            if period["reading"] in ("code-illisible", "illisible")
        )
        self.stdout.write(
            f"{len(proposals)} pages à corriger, dont {verified} déjà vérifiées (laissées par "
            f"défaut) ; {unreadable} décisions à relever sur le papier. Rapport : {path}"
        )
