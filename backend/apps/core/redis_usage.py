"""Mémoire de Redis (Render Key Value gratuit : 25 Mo, sans éviction, version 1.2.5).

Broker Celery, cache et temps réel partagent ce Redis. Plein, il refuse toute écriture : plus de
tâches publiées, plus de file d'attente des connexions. On le mesure pour prévenir avant :
contrôle d'intégrité (`check_integrity`) et avertissement dans l'application au CEO
(`apps.administration.tasks.watch_redis_memory`).
"""

from __future__ import annotations

from django.conf import settings

from .integrity import ERROR, WARNING, Check


def redis_memory() -> dict | None:
    """{"used", "limit", "pct"} en octets ; `pct` vaut None si la limite est inconnue.
    None si Redis ne répond pas."""
    import redis

    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1
        )
        info = client.info("memory")
    except Exception:
        return None
    used = int(info.get("used_memory", 0) or 0)
    limit = int(info.get("maxmemory", 0) or 0) or settings.REDIS_MAXMEMORY_BYTES
    pct = round(100 * used / limit, 1) if limit else None
    return {"used": used, "limit": limit, "pct": pct}


def check_redis_memory(options) -> Check:
    """Déclaré au registre INTEGRITY par apps/administration/hooks.py (dernier contrôle)."""
    check = Check(
        "redis_memory",
        WARNING,
        f"Redis a-t-il de la marge (alerte à {settings.REDIS_WARN_PCT} %) ?",
    )
    usage = redis_memory()
    if usage is None or usage["pct"] is None:
        return check
    if usage["pct"] >= 95:
        check.severity = ERROR
    if usage["pct"] >= settings.REDIS_WARN_PCT:
        used, limit = usage["used"] // 1024, usage["limit"] // 1024
        check.add(f"{usage['pct']} % utilisés ({used} Ko sur {limit} Ko)")
    return check
