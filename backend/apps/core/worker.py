"""Démarrage du worker Celery : reprise des analyses coupées et maintien en éveil (Render).

Les reprises et le travail en cours sont déclarés par les apps (`WORKER_START`,
`PENDING_WORK`, dans leur `hooks.py`).

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

from .registry import PENDING_WORK, WORKER_START

logger = logging.getLogger(__name__)


def has_pending_work() -> bool:
    """Une app déclare-t-elle du travail en cours (`PENDING_WORK`, dans son `hooks.py`) ?"""
    return any(probe() for probe in PENDING_WORK)


def run_start_hooks() -> None:
    """Reprises au démarrage du worker déclarées par les apps (`WORKER_START`)."""
    for hook in WORKER_START:
        try:
            hook()
        except Exception:
            logger.exception("Reprise au démarrage impossible : %s", hook.__qualname__)


def ping_if_busy(url: str) -> bool:
    """Une requête entrante sur l'adresse publique tant qu'il reste du travail."""
    if not has_pending_work():
        return False
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
        # Fil à part : sa propre connexion PostgreSQL, rendue après chaque vérification.
        close_old_connections()
        try:
            ping_if_busy(url)
        except Exception:
            logger.exception("Maintien en éveil : vérification impossible")
        finally:
            connection.close()


def on_worker_ready() -> None:
    if settings.WORKER_RESUME_INTERRUPTED:
        try:
            run_start_hooks()
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
