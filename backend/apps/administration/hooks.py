"""Ce que l'administration déclare au socle : le contrôle de la mémoire de Redis."""

from apps.core.redis_usage import check_redis_memory
from apps.core.registry import INTEGRITY

INTEGRITY.register(check_redis_memory)
