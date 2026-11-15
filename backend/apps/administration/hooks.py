"""Ce que l'administration déclare au socle : mémoire de Redis et sauvegardes de la base."""

from apps.core.backups import check_backups
from apps.core.redis_usage import check_redis_memory
from apps.core.registry import INTEGRITY

INTEGRITY.register(check_redis_memory)
INTEGRITY.register(check_backups)
