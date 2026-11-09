"""Contrôle des invariants métier, en lecture seule. À lancer après tout incident.

    python manage.py check_integrity                 # résumé lisible, code 1 si violation
    python manage.py check_integrity --json          # rapport machine (campagne de chaos)
    python manage.py check_integrity --skip-storage  # sans interroger le stockage des scans

Les invariants sont déclarés par les apps (`hooks.py`, `@INTEGRITY.register`) : le socle ne
connaît aucun modèle métier. Chaque invariant répond à une question posée après une panne : une
donnée a-t-elle été appliquée à moitié, dupliquée, perdue, ou référence-t-elle un fichier
disparu ?
Gravités : ERROR (donnée incohérente ou perdue, code de sortie 1), WARNING (fuite ou retard
sans perte, réparable), INFO.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.integrity import ERROR, IntegrityOptions, run_checks


class Command(BaseCommand):
    help = "Vérifie les invariants métier (lecture seule) ; code de sortie 1 en cas de violation."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="rapport JSON sur stdout")
        parser.add_argument(
            "--skip-storage", action="store_true", help="ne pas vérifier les fichiers stockés"
        )
        parser.add_argument(
            "--stuck-minutes",
            type=int,
            default=30,
            help="âge au-delà duquel une tâche ou un e-mail en attente est considéré perdu",
        )
        parser.add_argument(
            "--since",
            help="date ISO : ne juger que les alertes, e-mails et tâches créés après (les alertes "
            "de la mise en service, silencieuses par conception, n'ont pas de notification)",
        )

    def handle(self, *args, **options):
        started = timezone.now()
        checks = run_checks(
            IntegrityOptions(
                stuck_minutes=options["stuck_minutes"],
                since=options.get("since"),
                skip_storage=options["skip_storage"],
            )
        )
        report = {
            "checked_at": started.isoformat(),
            "duration_s": round((timezone.now() - started).total_seconds(), 2),
            "ok": not any(c.items for c in checks if c.severity == ERROR),
            "violations": {c.code: len(c.items) for c in checks if c.items},
            "checks": [c.as_dict() for c in checks],
        }
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, default=str))
        else:
            for check in checks:
                mark = "OK " if not check.items else check.severity
                count = len(check.items)
                self.stdout.write(f"[{mark:7}] {check.code:32} {count:6}  {check.question}")
                for item in check.items[:5]:
                    self.stdout.write(f"            - {item}")
            self.stdout.write(f"Intégrité : {'OK' if report['ok'] else 'VIOLATIONS'}")
        if not report["ok"]:
            raise SystemExit(1)
