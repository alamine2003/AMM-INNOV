"""Démarrage du worker Celery : reprise des analyses coupées et maintien en éveil (Render).

Sur Render gratuit, le worker tourne dans le conteneur du web. Le service est endormi après
15 minutes sans requête entrante (réglementaire parti déjeuner, onglet fermé) ou tué quand il
dépasse 512 Mo. Une analyse en cours y restait « Analyse en cours » 25 minutes puis passait en
échec, et les dossiers suivants attendaient le réveil suivant (25/09/2026, gamme Mali).
"""

import logging
import threading
import time
import urllib.request

from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
GAVE_UP = (
    "L'analyse a été interrompue {attempts} fois (redémarrage du serveur, mémoire). "
    "Relancez-la, ou déposez ce produit seul."
)


def resume_interrupted_analyses() -> dict:
    """Analyses « en cours » au démarrage du seul worker : reprises, ou abandonnées après
    MAX_ATTEMPTS essais (un dossier qui fait tomber le serveur ne boucle pas indéfiniment)."""
    from apps.imports.models import DossierImport
    from apps.imports.tasks import analyze_dossier

    running = DossierImport.objects.filter(status=DossierImport.Status.RUNNING)
    failed = running.filter(attempts__gte=MAX_ATTEMPTS)
    abandoned = 0
    for batch in failed:
        abandoned += DossierImport.objects.filter(
            pk=batch.pk, status=DossierImport.Status.RUNNING
        ).update(
            status=DossierImport.Status.FAILED,
            finished_at=timezone.now(),
            error=GAVE_UP.format(attempts=batch.attempts),
        )
    resumed = []
    for pk in running.filter(attempts__lt=MAX_ATTEMPTS).values_list("pk", flat=True):
        if DossierImport.objects.filter(pk=pk, status=DossierImport.Status.RUNNING).update(
            status=DossierImport.Status.PENDING, started_at=None
        ):
            resumed.append(str(pk))
    for pk in resumed:
        analyze_dossier.delay(pk)
    report = {"resumed": len(resumed), "abandoned": abandoned}
    if resumed or abandoned:
        logger.warning("Analyses interrompues au démarrage du worker : %s", report)
    return report


def has_pending_work() -> bool:
    from apps.imports.models import DossierImport, ImportBatch

    busy = [DossierImport.Status.PENDING, DossierImport.Status.RUNNING]
    return (
        DossierImport.objects.filter(status__in=busy).exists()
        or ImportBatch.objects.filter(
            status__in=[ImportBatch.Status.PENDING, ImportBatch.Status.RUNNING]
        ).exists()
    )


def ping_if_busy(url: str) -> bool:
    """Une requête entrante sur l'adresse publique tant qu'il reste du travail."""
    close_old_connections()
    try:
        if not has_pending_work():
            return False
    finally:
        connection.close()
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 (URL de config)
            response.read(64)
    except Exception as exc:
        logger.warning("Maintien en éveil : %s injoignable (%s)", url, exc)
        return False
    return True


def _keep_awake(url: str, every: int) -> None:
    while True:
        time.sleep(every)
        try:
            ping_if_busy(url)
        except Exception:
            logger.exception("Maintien en éveil : vérification impossible")


def on_worker_ready() -> None:
    if settings.WORKER_RESUME_INTERRUPTED:
        try:
            resume_interrupted_analyses()
        except Exception:
            logger.exception("Reprise des analyses interrompues impossible")
        finally:
            connection.close()
    url = settings.KEEPALIVE_URL
    if url and url.startswith(("http://", "https://")):
        threading.Thread(
            target=_keep_awake,
            args=(url, max(60, settings.KEEPALIVE_SECONDS)),
            name="amm-keepalive",
            daemon=True,
        ).start()
        logger.info("Maintien en éveil actif pendant les analyses : %s", url)
