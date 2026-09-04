"""WebSocket: JWT authentication in the query string, server-side group subscription."""

import pytest
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken

from apps.realtime.middleware import JWTAuthMiddleware
from apps.realtime.publisher import publish, publish_amm_event
from apps.realtime.routing import websocket_urlpatterns

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio]


def application():
    return JWTAuthMiddleware(URLRouter(websocket_urlpatterns))


async def connect(user):
    from asgiref.sync import sync_to_async

    token = await sync_to_async(lambda: str(RefreshToken.for_user(user).access_token))()
    communicator = WebsocketCommunicator(application(), f"/ws/?token={token}")
    connected, _ = await communicator.connect()
    assert connected
    hello = await communicator.receive_json_from()
    return communicator, hello


async def test_anonymous_connection_is_closed():
    communicator = WebsocketCommunicator(application(), "/ws/")
    connected, code = await communicator.connect()
    assert connected is False and code == 4401


async def test_country_user_groups_and_events(users, make_amm):
    from asgiref.sync import sync_to_async

    amm = await sync_to_async(make_amm)(country="SN")  # created before connecting
    communicator, hello = await connect(users["country"])
    expected = {"global", f"user.{users['country'].pk}", "country.SN", "country.ML"}
    assert set(hello["groups"]) == expected

    await sync_to_async(publish_amm_event)("amm.updated", amm)
    event = await communicator.receive_json_from()
    assert event == {"type": "amm.updated", "id": str(amm.pk), "country": "SN"}
    # the same event was also sent on `global`, which the user joined too
    assert (await communicator.receive_json_from())["type"] == "amm.updated"

    await sync_to_async(publish)("country.CI", {"type": "amm.updated", "id": "x", "country": "CI"})
    assert await communicator.receive_nothing(timeout=0.2)
    await communicator.send_json_to({"type": "ping"})
    assert await communicator.receive_json_from() == {"type": "pong"}
    await communicator.disconnect()


async def test_global_user_joins_every_country(users, countries):
    communicator, hello = await connect(users["hq"])
    assert {"country.SN", "country.ML", "country.CI", "country.GN"} <= set(hello["groups"])
    await communicator.disconnect()
