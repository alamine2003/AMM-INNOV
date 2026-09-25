"""Archive les documents communs d'un dossier pays rangés dans une fiche hors sujet."""

from django.core.management.base import BaseCommand

from apps.imports.dossier.cleanup import detach_unrelated_common_documents


class Command(BaseCommand):
    help = (
        "Relit les documents communs des dossiers pays déjà rangés et archive ceux qui ne "
        "concernent pas le produit de leur fiche (--dry-run : liste sans modifier)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, dry_run=False, **options):
        report = detach_unrelated_common_documents(dry_run=dry_run)
        self.stdout.write(str(report))
