"""Dégradation propre quand Redis ne répond plus (campagne de chaos, docs/audit-resilience).

Redis porte ici des fonctions *accessoires* à la requête : temps réel, cache du throttle de
connexion, publication de tâches. Mesuré sur le laboratoire, chacune payait jusqu'à 5 s par
appel quand Redis était coupé ou figé, trois fois par écriture, en tenant une connexion du
pool PostgreSQL : sous charge, les lectures tombaient à leur tour (scénario s03c).

`REDIS_BREAKER` (temps réel, cache) et `BROKER_BREAKER` (file des tâches) coupent ce couplage :
après un échec, les appels suivants sont court-circuités pendant `cooldown` secondes (état
« ouvert »), puis un seul appel d'essai décide de la reprise.
"""

from __future__ import annotations

import logging
import threading
import time

from django.core.cache.backends.locmem import LocMemCache
from prometheus_client import Counter

logger = logging.getLogger(__name__)

DEGRADED = Counter(
    "amm_degraded_operations",
    "Opérations sautées ou repliées parce qu'une dépendance ne répondait pas",
    ["component"],
)


class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, name: str, cooldown: float = 15.0):
        self.name, self.cooldown = name, cooldown
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.state = self.CLOSED
        self._opened_at = 0.0

    def allow(self) -> bool:
        """True si l'appel peut partir ; en demi-ouverture, un seul appel d'essai à la fois."""
        with self._lock:
            if self.state == self.CLOSED:
                return True
            # ouvert depuis `cooldown`, ou essai précédent resté sans nouvelles : nouvel essai
            if time.monotonic() - self._opened_at >= self.cooldown:
                self.state = self.HALF_OPEN
                self._opened_at = time.monotonic()
                return True
            return False

    def success(self) -> None:
        if self.state != self.CLOSED:
            logger.warning("%s : dépendance rétablie, disjoncteur refermé", self.name)
        self.state = self.CLOSED

    def failure(self) -> None:
        with self._lock:
            if self.state != self.OPEN:
                logger.error(
                    "%s : dépendance indisponible, appels suspendus %.0f s",
                    self.name,
                    self.cooldown,
                )
            self.state = self.OPEN
            self._opened_at = time.monotonic()


REDIS_BREAKER = CircuitBreaker("redis")
# Disjoncteur distinct pour la file des tâches : une lenteur du temps réel ne doit pas faire
# sauter la publication d'une analyse de dossier, et une vraie panne du broker ne doit pas faire
# attendre chaque upload (relecture et rejeu s03a).
BROKER_BREAKER = CircuitBreaker("broker")


class ResilientCache:
    """Cache du throttle de connexion : Redis, et mémoire locale du processus s'il tombe.

    Sans ce repli, Redis indisponible = plus personne ne se connecte (s03a : 13/13 connexions en
    500). Le repli garde la protection anti force brute, par processus au lieu de globale.
    """

    def __init__(self, alias: str = "default"):
        self.alias = alias
        self.local = LocMemCache("throttle-fallback", {"OPTIONS": {"MAX_ENTRIES": 10000}})

    @property
    def remote(self):
        from django.core.cache import caches

        return caches[self.alias]

    def _call(self, name: str, *args, **kwargs):
        if REDIS_BREAKER.allow():
            try:
                result = getattr(self.remote, name)(*args, **kwargs)
                REDIS_BREAKER.success()
                return result
            except Exception:
                REDIS_BREAKER.failure()
                logger.warning("cache Redis indisponible : repli local pour %s", name)
        DEGRADED.labels("throttle_cache").inc()
        return getattr(self.local, name)(*args, **kwargs)

    def get(self, key, default=None):
        return self._call("get", key, default)

    def set(self, key, value, timeout=None):
        return self._call("set", key, value, timeout)
