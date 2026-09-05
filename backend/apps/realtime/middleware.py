"""ASGI middleware authenticating WebSocket connections with the access JWT.

The token travels in the `Sec-WebSocket-Protocol` header (`amm.jwt, <token>`), never in the
URL: query strings end up in proxy access logs, request headers do not. The consumer echoes
the `amm.jwt` sub-protocol back when accepting.
"""

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser

SUBPROTOCOL = "amm.jwt"


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


def token_from_scope(scope) -> str | None:
    """`Sec-WebSocket-Protocol: amm.jwt, <token>` -> token (None when absent)."""
    offered = [p.strip() for p in (scope.get("subprotocols") or [])]
    if SUBPROTOCOL in offered:
        candidates = [p for p in offered if p != SUBPROTOCOL]
        if candidates:
            return candidates[0]
    return None


class JWTAuthMiddleware:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        token = token_from_scope(scope)
        scope["user"] = await user_from_token(token) if token else AnonymousUser()
        return await self.inner(scope, receive, send)
