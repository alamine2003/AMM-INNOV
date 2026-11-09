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

from apps.core.registry import RECOVERY
from apps.core.resilience import BROKER_BREAKER, DEGRADED

logger = logging.getLogger(__name__)


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
    vérifie elle-même qu'elle n'a pas déjà été faite (sent_at, page_count, statut).

    Le travail à rattraper est déclaré par chaque app (`RECOVERY`, dans son `hooks.py`)."""
    now = timezone.now()
    report: dict[str, int] = {}
    for recover in RECOVERY:
        report.update(recover(now))
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
