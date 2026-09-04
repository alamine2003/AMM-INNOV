"""WebSocket consumer: joins the user's groups (computed server-side) and relays events."""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.core import metrics

from .publisher import GLOBAL_GROUP, country_group, user_group


@database_sync_to_async
def groups_for_user(user) -> list[str]:
    from apps.catalog.models import Country

    if user.is_global:
        iso2s = list(Country.objects.values_list("iso2", flat=True))
    else:
        iso2s = list(user.countries.values_list("iso2", flat=True))
    return [GLOBAL_GROUP, user_group(user.pk)] + [country_group(code) for code in iso2s]


class EventConsumer(AsyncJsonWebsocketConsumer):
    groups: list[str] = []

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.joined = await groups_for_user(user)
        for group in self.joined:
            await self.channel_layer.group_add(group, self.channel_name)
        await self.accept()
        await database_sync_to_async(metrics.ws_connected)()
        await self.send_json({"type": "connected", "groups": self.joined})

    async def disconnect(self, code):
        if getattr(self, "joined", None):
            await database_sync_to_async(metrics.ws_disconnected)()
        for group in getattr(self, "joined", []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def event_message(self, event):
        await self.send_json(event["payload"])
