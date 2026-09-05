from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.alerts.services.engine import evaluate_rules


class Command(BaseCommand):
    help = (
        "Évalue les règles d'alerte pour toutes les AMM (ce que fait Celery beat chaque nuit). "
        "--quiet crée les alertes sans aucune notification : à utiliser lors de la première "
        "mise en service, après l'import de l'historique, pour éviter un déluge d'emails."
    )

    def add_arguments(self, parser):
        parser.add_argument("--today", help="Date de référence AAAA-MM-JJ (défaut : aujourd'hui)")
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Crée les alertes manquantes sans envoyer de notification (in-app ni email).",
        )

    def handle(self, *args, **options):
        today = None
        if options["today"]:
            try:
                today = date.fromisoformat(options["today"])
            except ValueError as exc:
                raise CommandError("--today attend une date AAAA-MM-JJ") from exc
        result = evaluate_rules(today=today, dispatch=not options["quiet"])
        self.stdout.write(
            self.style.SUCCESS(
                f"{result['evaluated']} AMM évaluées, {result['created']} alerte(s) créée(s), "
                f"{result['notified']} notifiée(s), {result['silenced']} silencieuse(s)."
            )
        )
