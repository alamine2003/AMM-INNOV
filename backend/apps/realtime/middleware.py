"""ASGI middleware authenticating WebSocket connections with `?token=<access JWT>`."""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def user_from_token(raw_token: str):
    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.exceptions import TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        token = AccessToken(raw_token)
        user = get_user_model().objects.get(pk=token["user_id"], is_active=True)
    except (TokenError, KeyError, get_user_model().DoesNotExist, ValueError):
        return AnonymousUser()
    return user


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        scope["user"] = await user_from_token(token) if token else AnonymousUser()
        return await self.inner(scope, receive, send)
