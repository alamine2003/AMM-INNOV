"""ASGI entry point: HTTP through Django, WebSocket through Channels (Daphne)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import OriginValidator  # noqa: E402
from django.conf import settings  # noqa: E402

from apps.realtime.middleware import JWTAuthMiddleware  # noqa: E402
from apps.realtime.routing import websocket_urlpatterns  # noqa: E402


def websocket_allowed_origins() -> list[str]:
    """Origines WebSocket acceptées : les origines CORS (frontend sur son propre domaine, par
    exemple Netlify face à une API Render) et les hôtes de l'API (frontend servi par nginx)."""
    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False) or "*" in settings.ALLOWED_HOSTS:
        return ["*"]
    return list(settings.CORS_ALLOWED_ORIGINS) + list(settings.ALLOWED_HOSTS)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": OriginValidator(
            JWTAuthMiddleware(URLRouter(websocket_urlpatterns)), websocket_allowed_origins()
        ),
    }
)
