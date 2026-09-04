"""`python manage.py import_excel <path> [--user email] [--today AAAA-MM-JJ]`."""

import json
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from apps.imports.models import ImportBatch
from apps.imports.services import import_workbook


class Command(BaseCommand):
    help = "Importe le classeur Excel de suivi des AMM (onglets au format normalisé)."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Chemin du classeur .xlsx")
        parser.add_argument("--user", help="Email de l'utilisateur à l'origine de l'import")
        parser.add_argument(
            "--today", help="Date de référence AAAA-MM-JJ pour le calcul des statuts"
        )
        parser.add_argument(
            "--no-batch", action="store_true", help="Ne pas enregistrer d'ImportBatch"
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"Fichier introuvable : {path}")
        today = date.fromisoformat(options["today"]) if options.get("today") else None
        user = None
        if options.get("user"):
            user = get_user_model().objects.filter(email=options["user"].lower()).first()
            if user is None:
                raise CommandError(f"Utilisateur inconnu : {options['user']}")
        batch = None
        if not options["no_batch"]:
            batch = ImportBatch(created_by=user, reference_date=today)
            with path.open("rb") as handle:
                batch.file.save(path.name, File(handle), save=True)
        summary = import_workbook(str(path), batch=batch, today=today)
        self.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
        totals = summary.get("totals", {})
        self.stdout.write(
            self.style.SUCCESS(
                f"Import terminé : {totals.get('rows', 0)} lignes, "
                f"{totals.get('created', 0)} créées, "
                f"{totals.get('updated', 0)} mises à jour, {totals.get('skipped', 0)} inchangées, "
                f"{totals.get('errors', 0)} erreurs, {totals.get('warnings', 0)} avertissements."
            )
        )
