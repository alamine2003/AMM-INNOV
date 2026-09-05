"""Production settings: TLS terminated by nginx, secure cookies, strict hosts."""

from .base import *  # noqa: F403
from .base import env, env_bool

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_CONTENT_TYPE_NOSNIFF = True
# Render, Caddy et nginx terminent TLS et transmettent X-Forwarded-For : un proxy devant Django.
REST_FRAMEWORK["NUM_PROXIES"] = int(env("NUM_PROXIES", "1"))  # noqa: F405
CSRF_TRUSTED_ORIGINS = [o for o in (env("CSRF_TRUSTED_ORIGINS") or "").split(",") if o]

# Render renseigne RENDER_EXTERNAL_HOSTNAME avec l'hôte réellement attribué au service (qui peut
# différer du nom demandé si celui-ci est pris) : on l'accepte d'office, sinon la sonde de santé
# recevrait un 400 « hôte non autorisé » et le déploiement serait refusé.
RENDER_HOST = env("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, RENDER_HOST]))  # noqa: F405
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([*CSRF_TRUSTED_ORIGINS, f"https://{RENDER_HOST}"]))
