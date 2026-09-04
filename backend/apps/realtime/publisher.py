"""Publishes domain events to Channels groups (`user.<id>`, `country.<ISO2>`, `global`).

Events only carry identifiers; clients reload data through the REST API.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

GLOBAL_GROUP = "global"


def user_group(user_id) -> str:
    return f"user.{user_id}"


def country_group(iso2: str) -> str:
    return f"country.{iso2.upper()}"


def publish(group: str, payload: dict) -> None:
    """Sends `payload` to every consumer subscribed to `group`; never raises."""
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, {"type": "event.message", "payload": payload})
    except Exception:  # pragma: no cover - the channel layer must never break a request
        logger.warning("Impossible de publier l'événement %s sur %s", payload.get("type"), group)


def publish_amm_event(event_type: str, amm, **extra) -> None:
    iso2 = amm.country.iso2 if amm.country_id else None
    payload = {"type": event_type, "id": str(amm.pk), "country": iso2, **extra}
    if iso2:
        publish(country_group(iso2), payload)
    publish(GLOBAL_GROUP, payload)


def publish_dashboard_refresh() -> None:
    publish(GLOBAL_GROUP, {"type": "dashboard.refresh", "id": None, "country": None})


def publish_user_event(user_id, event_type: str, object_id, country: str | None = None) -> None:
    publish(user_group(user_id), {"type": event_type, "id": str(object_id), "country": country})
