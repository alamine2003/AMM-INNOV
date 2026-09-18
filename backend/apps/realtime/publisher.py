"""Publishes domain events to Channels groups (`user.<id>`, `country.<ISO2>`, `global`).

Events only carry identifiers; clients reload data through the REST API.

Le temps réel est un confort, jamais une condition d'une écriture (campagne de chaos,
docs/audit-resilience, s03/s04) :
- la publication part après le commit : aucun verrou ni connexion du pool n'est tenu pendant
  l'appel à Redis, et une transaction annulée n'annonce rien ;
- elle est bornée à PUBLISH_TIMEOUT et suspendue par le disjoncteur Redis quand Redis ne répond
  plus : les clients retombent sur leur polling de 60 s.
- un événement d'AMM ne part que vers le groupe de son pays : les rôles globaux sont membres de
  tous les groupes pays, et le doubler sur `global` le faisait recevoir à tous les clients.
"""

import asyncio
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from apps.core.resilience import DEGRADED, REDIS_BREAKER

logger = logging.getLogger(__name__)

GLOBAL_GROUP = "global"
PUBLISH_TIMEOUT = 1.0


def user_group(user_id) -> str:
    return f"user.{user_id}"


def country_group(iso2: str) -> str:
    return f"country.{iso2.upper()}"


def publish(group: str, payload: dict) -> None:
    """Sends `payload` to every consumer of `group` once the transaction commits; never raises."""
    transaction.on_commit(lambda: _send(group, payload))


async def _bounded_send(layer, group: str, message: dict) -> None:
    await asyncio.wait_for(layer.group_send(group, message), timeout=PUBLISH_TIMEOUT)


def _send(group: str, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    if not REDIS_BREAKER.allow():
        DEGRADED.labels("realtime_publish").inc()
        return
    try:
        async_to_sync(_bounded_send)(layer, group, {"type": "event.message", "payload": payload})
    except Exception:  # le temps réel ne doit jamais casser une requête
        REDIS_BREAKER.failure()
        DEGRADED.labels("realtime_publish").inc()
        logger.warning("Impossible de publier l'événement %s sur %s", payload.get("type"), group)
        return
    REDIS_BREAKER.success()


def publish_amm_event(event_type: str, amm, **extra) -> None:
    iso2 = amm.country.iso2 if amm.country_id else None
    payload = {"type": event_type, "id": str(amm.pk), "country": iso2, **extra}
    publish(country_group(iso2) if iso2 else GLOBAL_GROUP, payload)


def publish_dashboard_refresh() -> None:
    """Traitements de masse (import, recalcul nocturne) : tous les tableaux de bord à recharger."""
    publish(GLOBAL_GROUP, {"type": "dashboard.refresh", "id": None, "country": None})


def publish_user_event(user_id, event_type: str, object_id, country: str | None = None) -> None:
    publish(user_group(user_id), {"type": event_type, "id": str(object_id), "country": country})
