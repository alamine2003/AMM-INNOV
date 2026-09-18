"""Publication des tâches Celery et rattrapage du travail perdu.

`enqueue()` publie une tâche après le commit. Si Redis ne répond pas, la publication échoue
*sans* faire échouer la requête : la donnée est déjà enregistrée (s03a : un upload restait
bloqué plus de 60 s puis revenait en erreur alors que le scan était en base, et l'utilisateur
le renvoyait). Le travail non publié n'est pas perdu : `recover_pending_work` le retrouve en
base et le republie.

In eager mode (tests) the task runs immediately so that results are observable.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.resilience import BROKER_BREAKER, DEGRADED

logger = logging.getLogger(__name__)

# Au-delà (~5 h de panne Gmail couvertes, par exemple un quota d'envoi journalier dépassé), un
# e-mail est abandonné : l'échec reste visible (last_error, v_ops_backlog, check_integrity).
MAX_EMAIL_ATTEMPTS = 60
EMAIL_RETRY_AFTER = timedelta(minutes=15)  # laisse finir les relances Celery (≈ 10 min)
DOSSIER_PENDING_AFTER = timedelta(minutes=5)
DOSSIER_RUNNING_MAX = timedelta(minutes=25)  # soft_time_limit de l'analyse : 20 min
PREVIEW_AFTER = timedelta(minutes=10)


def enqueue(task, *args, **kwargs) -> None:
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        task.apply(args=args, kwargs=kwargs)
        return
    transaction.on_commit(lambda: _publish(task, args, kwargs))


def _publish(task, args, kwargs) -> None:
    if not BROKER_BREAKER.allow():
        DEGRADED.labels("task_publish").inc()
        logger.warning("File de tâches indisponible : %s sera rattrapée", task.name)
        return
    try:
        task.delay(*args, **kwargs)
    except Exception:
        BROKER_BREAKER.failure()
        DEGRADED.labels("task_publish").inc()
        logger.exception("Publication impossible de %s : elle sera rattrapée", task.name)
        return
    BROKER_BREAKER.success()


@shared_task(name="apps.core.tasks.recover_pending_work")
def recover_pending_work() -> dict:
    """Republie ce que la base déclare encore à faire. Idempotent : chaque tâche relancée
    vérifie elle-même qu'elle n'a pas déjà été faite (sent_at, page_count, statut)."""
    from apps.documents.models import Document
    from apps.documents.tasks import generate_document_preview
    from apps.imports.models import DossierImport, ImportBatch
    from apps.imports.tasks import analyze_dossier, run_import
    from apps.notifications.models import Notification
    from apps.notifications.tasks import send_alert_email

    now = timezone.now()
    report = {
        "emails": 0,
        "dossiers_republished": 0,
        "dossiers_interrupted": 0,
        "imports_republished": 0,
        "previews": 0,
    }

    emails = Notification.objects.filter(
        channel=Notification.Channel.EMAIL,
        sent_at__isnull=True,
        send_attempts__lt=MAX_EMAIL_ATTEMPTS,
        created_at__lt=now - EMAIL_RETRY_AFTER,
        created_at__gte=now - timedelta(days=2),
    ).exclude(last_attempt_at__gte=now - EMAIL_RETRY_AFTER)
    for pk in emails.values_list("pk", flat=True)[:500]:
        send_alert_email.delay(str(pk))
        report["emails"] += 1

    interrupted = DossierImport.objects.filter(
        status=DossierImport.Status.RUNNING, started_at__lt=now - DOSSIER_RUNNING_MAX
    ).update(
        status=DossierImport.Status.FAILED,
        finished_at=now,
        error="L'analyse a été interrompue (redémarrage du service). Relancez l'analyse.",
    )
    report["dossiers_interrupted"] = interrupted
    pending = DossierImport.objects.filter(
        status=DossierImport.Status.PENDING, created_at__lt=now - DOSSIER_PENDING_AFTER
    )
    for pk in pending.values_list("pk", flat=True)[:100]:
        analyze_dossier.delay(str(pk))
        report["dossiers_republished"] += 1

    imports = ImportBatch.objects.filter(
        status=ImportBatch.Status.PENDING, created_at__lt=now - DOSSIER_PENDING_AFTER
    )
    for pk in imports.values_list("pk", flat=True)[:20]:
        run_import.delay(str(pk))  # prise en charge exclusive dans la tâche : pas de doublon
        report["imports_republished"] += 1

    previews = Document.objects.filter(
        page_count__isnull=True,
        content_type="application/pdf",
        uploaded_at__lt=now - PREVIEW_AFTER,
        uploaded_at__gte=now - timedelta(days=1),
    )
    for pk in previews.values_list("pk", flat=True)[:500]:
        generate_document_preview.delay(str(pk))
        report["previews"] += 1

    if any(report.values()):
        logger.warning("Rattrapage du travail en attente : %s", report)
    return report


@shared_task(name="apps.core.tasks.check_integrity")
def check_integrity() -> dict:
    """Invariants métier chaque nuit : une violation est journalisée en ERROR (alerte)."""
    import json
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    since = (timezone.now() - timedelta(days=1)).isoformat()
    try:
        call_command("check_integrity", "--json", "--since", since, stdout=out)
    except SystemExit:
        pass
    report = json.loads(out.getvalue())
    if not report["ok"]:
        logger.error("Intégrité : violations %s", report["violations"])
    return report["violations"]
