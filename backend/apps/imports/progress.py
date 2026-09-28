"""Avancement d'un import en cours, lisible pendant qu'il tourne.

L'import travaille dans une transaction (la simulation est annulée à la fin) : ce qu'il écrit en
base n'est visible qu'une fois fini. L'avancement passe donc par le cache (Redis), hors
transaction. Le cache en panne ne gêne jamais l'import : l'écran affiche alors un avancement
indéterminé.
"""

import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)
TTL = 6 * 3600


def _key(batch_id) -> str:
    return f"imports:progress:{batch_id}"


def set_progress(batch_id, done: int, total: int) -> None:
    try:
        cache.set(_key(batch_id), {"done": done, "total": total}, TTL)
    except Exception:  # le cache ne doit jamais faire échouer un import
        logger.debug("Avancement de l'import %s non enregistré", batch_id)


def get_progress(batch_id) -> dict | None:
    try:
        return cache.get(_key(batch_id))
    except Exception:
        return None
