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
# Railway, Render, Caddy et nginx terminent TLS et transmettent X-Forwarded-For :
# un seul proxy devant Django.
REST_FRAMEWORK["NUM_PROXIES"] = int(env("NUM_PROXIES", "1"))  # noqa: F405
CSRF_TRUSTED_ORIGINS = [o for o in (env("CSRF_TRUSTED_ORIGINS") or "").split(",") if o]

# La plateforme renseigne l'hôte public réellement attribué au service (Railway :
# RAILWAY_PUBLIC_DOMAIN, Render : RENDER_EXTERNAL_HOSTNAME) : on l'accepte d'office, sinon la
# sonde de santé recevrait un 400 « hôte non autorisé » et le déploiement serait refusé.
# Railway : RAILWAY_PRIVATE_DOMAIN sert aux appels internes (sonde, autres services).
PLATFORM_HOSTS = [
    h
    for h in (
        env("RAILWAY_PUBLIC_DOMAIN"),
        env("RAILWAY_PRIVATE_DOMAIN"),
        env("RENDER_EXTERNAL_HOSTNAME"),
    )
    if h
]
if PLATFORM_HOSTS:
    ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, *PLATFORM_HOSTS]))  # noqa: F405
    CSRF_TRUSTED_ORIGINS = list(
        dict.fromkeys([*CSRF_TRUSTED_ORIGINS, *(f"https://{h}" for h in PLATFORM_HOSTS)])
    )
