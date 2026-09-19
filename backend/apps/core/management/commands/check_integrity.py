"""Contrôle des invariants métier, en lecture seule. À lancer après tout incident.

    python manage.py check_integrity                 # résumé lisible, code 1 si violation
    python manage.py check_integrity --json          # rapport machine (campagne de chaos)
    python manage.py check_integrity --skip-storage  # sans interroger le stockage des scans

Chaque invariant répond à une question posée après une panne : une donnée a-t-elle été
appliquée à moitié, dupliquée, perdue, ou référence-t-elle un fichier disparu ?
Gravités : ERROR (donnée incohérente ou perdue, code de sortie 1), WARNING (fuite ou retard
sans perte, réparable), INFO.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count, F, Q
from django.utils import timezone

ERROR, WARNING = "ERROR", "WARNING"

# Champs saisis par un utilisateur : l'historique doit toujours refléter la ligne courante.
# Les champs calculés (statut, urgence…) sont réécrits la nuit par update() sans historique.
AMM_TRACKED = (
    "original_number",
    "holder",
    "original_start_date",
    "original_end_date",
    "original_end_date_manual",
    "notes",
    "owner_id",
    "product_id",
    "country_id",
)
RENEWAL_TRACKED = (
    "workflow_status",
    "number",
    "filing_date",
    "decision_date",
    "start_date",
    "end_date",
    "notes",
)
SAMPLE = 20


class Check:
    def __init__(self, code: str, severity: str, question: str):
        self.code, self.severity, self.question = code, severity, question
        self.items: list[str] = []

    def add(self, item) -> None:
        self.items.append(str(item))

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "question": self.question,
            "count": len(self.items),
            "sample": self.items[:SAMPLE],
        }


def _latest_history(model, ids_field: str = "id"):
    """{object id: latest historical row} — DISTINCT ON sous PostgreSQL."""
    history = model.history.model.objects.all()
    if connection.vendor == "postgresql":
        rows = history.order_by(ids_field, "-history_date", "-history_id").distinct(ids_field)
        return {getattr(row, ids_field): row for row in rows}
    latest = {}
    for row in history.order_by("history_date", "history_id"):
        latest[getattr(row, ids_field)] = row
    return latest


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
        checks = [
            self.check_amm_state(),
            self.check_single_open_renewal(),
            self.check_renewal_sequences(),
            self.check_history_matches_rows(),
            self.check_document_versions(),
            self.check_document_links(),
            self.check_duplicate_notifications(),
            self.check_alerts_without_notification(options.get("since")),
            self.check_unsent_emails(options["stuck_minutes"], options.get("since")),
            self.check_stuck_jobs(options["stuck_minutes"], options.get("since")),
        ]
        if not options["skip_storage"]:
            checks.extend(self.check_storage())
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

    # --- AMM ---------------------------------------------------------------

    def check_amm_state(self) -> Check:
        from apps.amm.models import MarketingAuthorization
        from apps.amm.services.status import compute_amm_state, current_scans_prefetch

        check = Check(
            "amm_state_consistent",
            ERROR,
            "Le statut stocké de chaque AMM correspond-il à ses renouvellements et scans ?",
        )
        queryset = MarketingAuthorization.objects.select_related("country").prefetch_related(
            "renewals", current_scans_prefetch()
        )
        for amm in queryset.iterator(chunk_size=500):
            state = compute_amm_state(
                amm, renewals=list(amm.renewals.all()), documents=list(amm.current_scans)
            )
            if state.differs_from(amm):
                check.add(
                    f"{amm.pk}: stocké {amm.status}/{amm.urgency}/{amm.effective_end_date}/"
                    f"{amm.dossier_state} ≠ attendu {state.status}/{state.urgency}/"
                    f"{state.effective_end_date}/{state.dossier_state}"
                )
        return check

    def check_single_open_renewal(self) -> Check:
        from apps.amm.models import Renewal

        check = Check(
            "single_open_renewal", ERROR, "Au plus un renouvellement ouvert par AMM ?"
        )
        rows = (
            Renewal.objects.filter(workflow_status__in=Renewal.OPEN_STATUSES)
            .values("amm_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        for row in rows:
            check.add(f"AMM {row['amm_id']}: {row['n']} renouvellements ouverts")
        return check

    def check_renewal_sequences(self) -> Check:
        from apps.amm.models import Renewal

        check = Check(
            "renewal_sequence_contiguous",
            WARNING,
            "Les n° d'ordre des renouvellements forment-ils une suite 1..n ?",
        )
        by_amm = defaultdict(list)
        for amm_id, sequence in Renewal.objects.values_list("amm_id", "sequence"):
            by_amm[amm_id].append(sequence)
        for amm_id, sequences in by_amm.items():
            if sorted(sequences) != list(range(1, len(sequences) + 1)):
                check.add(f"AMM {amm_id}: {sorted(sequences)}")
        return check

    def check_history_matches_rows(self) -> Check:
        from apps.amm.models import MarketingAuthorization, Renewal

        check = Check(
            "history_matches_rows",
            ERROR,
            "La dernière entrée d'historique reflète-t-elle la ligne "
            "(aucune écriture sans trace) ?",
        )
        for model, fields, label in (
            (MarketingAuthorization, AMM_TRACKED, "AMM"),
            (Renewal, RENEWAL_TRACKED, "Renouvellement"),
        ):
            latest = _latest_history(model)
            for obj in model.objects.all().iterator(chunk_size=1000):
                row = latest.get(obj.pk)
                if row is None:
                    check.add(f"{label} {obj.pk}: aucune entrée d'historique")
                    continue
                diff = [f for f in fields if getattr(obj, f) != getattr(row, f)]
                if diff:
                    check.add(f"{label} {obj.pk}: {', '.join(diff)} modifiés sans historique")
        return check

    # --- Documents ---------------------------------------------------------

    def check_document_versions(self) -> Check:
        from apps.documents.models import Document

        check = Check(
            "single_current_version",
            ERROR,
            "Un document remplacé n'est-il plus courant, "
            "et une version n'a-t-elle qu'un seul successeur ?",
        )
        stale = Document.objects.filter(
            is_current=True, archived_at__isnull=True, replaced_by__isnull=False
        ).distinct()
        for document in stale.values_list("pk", flat=True):
            check.add(f"document {document}: encore courant alors qu'une version le remplace")
        forks = (
            Document.objects.filter(replaces__isnull=False, archived_at__isnull=True)
            .order_by()  # le tri imposé par le manager entrerait dans le GROUP BY
            .values("replaces_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        for row in forks:
            check.add(f"document {row['replaces_id']}: {row['n']} successeurs actifs")
        return check

    def check_document_links(self) -> Check:
        from apps.documents.models import Document

        check = Check(
            "document_renewal_same_amm",
            ERROR,
            "Un scan rattaché à un renouvellement appartient-il à la même AMM ?",
        )
        crossed = Document.objects.filter(renewal__isnull=False).exclude(
            renewal__amm_id=F("amm_id")
        )
        for pk in crossed.values_list("pk", flat=True):
            check.add(f"document {pk}")
        return check

    def check_storage(self) -> list[Check]:
        from django.core.files.storage import default_storage

        from apps.documents.models import Document
        from apps.imports.models import DossierFile

        missing = Check(
            "referenced_file_exists",
            ERROR,
            "Chaque fichier référencé en base existe-t-il dans le stockage ?",
        )
        orphans = Check(
            "orphan_blobs",
            WARNING,
            "Le stockage contient-il des fichiers qu'aucune ligne ne référence (fuite) ?",
        )
        referenced = set()
        for model in (Document, DossierFile):
            for pk, name in model.objects.values_list("pk", "file"):
                if not name:
                    continue
                referenced.add(name)
                if not default_storage.exists(name):
                    missing.add(f"{model.__name__} {pk}: {name}")
        for name in _list_blobs(default_storage, "documents/"):
            if name not in referenced:
                orphans.add(name)
        return [missing, orphans]

    # --- Alertes, notifications, tâches -----------------------------------

    def check_duplicate_notifications(self) -> Check:
        from apps.notifications.models import Notification

        check = Check(
            "no_duplicate_notification",
            ERROR,
            "Une alerte n'a-t-elle notifié chaque destinataire qu'une fois par canal ?",
        )
        rows = (
            Notification.objects.filter(alert__isnull=False)
            .values("alert_id", "user_id", "channel")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
        )
        for row in rows:
            check.add(f"alerte {row['alert_id']} → {row['user_id']} ({row['channel']}) ×{row['n']}")
        return check

    def check_alerts_without_notification(self, since: str | None = None) -> Check:
        from apps.alerts.models import Alert
        from apps.notifications.services import recipients_for

        check = Check(
            "fresh_alert_notified",
            ERROR,
            "Une alerte récente (non silencieuse par conception) a-t-elle bien été notifiée ?",
        )
        max_age = settings.ALERTS_DISPATCH_MAX_AGE_DAYS
        candidates = (
            Alert.objects.filter(notifications__isnull=True)
            .select_related("rule", "amm__country")
            .exclude(rule__channels=[])
        )
        if since:
            candidates = candidates.filter(triggered_at__gte=since)
        for alert in candidates.iterator(chunk_size=500):
            fresh = (alert.triggered_at.date() - alert.due_date).days <= max_age
            if fresh and recipients_for(alert):
                check.add(f"alerte {alert.pk} ({alert.rule.code}, échéance {alert.due_date})")
        return check

    def check_unsent_emails(self, minutes: int, since: str | None = None) -> Check:
        from apps.notifications.models import Notification

        check = Check(
            "email_delivered",
            ERROR,
            f"Un e-mail d'alerte reste-t-il non envoyé plus de {minutes} min après sa création ?",
        )
        limit = timezone.now() - timedelta(minutes=minutes)
        rows = Notification.objects.filter(
            channel=Notification.Channel.EMAIL, sent_at__isnull=True, created_at__lt=limit
        )
        if since:
            rows = rows.filter(created_at__gte=since)
        for pk in rows.values_list("pk", flat=True):
            check.add(f"notification {pk}")
        return check

    def check_stuck_jobs(self, minutes: int, since: str | None = None) -> Check:
        from apps.imports.models import DossierImport, ImportBatch

        check = Check(
            "no_stuck_job",
            ERROR,
            f"Un import ou une analyse de dossier est-il bloqué depuis plus de {minutes} min ?",
        )
        limit = timezone.now() - timedelta(minutes=minutes)
        for model in (ImportBatch, DossierImport):
            stuck = model.objects.filter(
                Q(status=model.Status.PENDING) | Q(status=model.Status.RUNNING),
                created_at__lt=limit,
            )
            if since:
                stuck = stuck.filter(created_at__gte=since)
            for pk, status in stuck.values_list("pk", "status"):
                check.add(f"{model.__name__} {pk}: {status}")
        return check


def _list_blobs(storage, prefix: str):
    """Tous les fichiers sous `prefix`, en local comme sur S3."""
    bucket = getattr(storage, "bucket", None)
    if bucket is not None:  # S3Storage (django-storages)
        location = getattr(storage, "location", "") or ""
        base = f"{location.rstrip('/')}/" if location else ""
        for obj in bucket.objects.filter(Prefix=base + prefix):
            yield obj.key[len(base):]
        return
    try:
        directories, files = storage.listdir(prefix)
    except (FileNotFoundError, NotImplementedError):
        return
    for name in files:
        yield f"{prefix}{name}"
    for directory in directories:
        yield from _list_blobs(storage, f"{prefix}{directory}/")
