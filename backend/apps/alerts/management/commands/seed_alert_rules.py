from django.core.management.base import BaseCommand

from apps.alerts.defaults import seed_default_rules
from apps.alerts.models import AlertRule


class Command(BaseCommand):
    help = "Crée les règles d'alerte globales par défaut (J-365, J-180, J-90, J-30, J0, DOSSIER)."

    def handle(self, *args, **options):
        created = seed_default_rules(AlertRule)
        self.stdout.write(self.style.SUCCESS(f"{created} règle(s) créée(s)."))
