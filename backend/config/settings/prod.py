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
CSRF_TRUSTED_ORIGINS = [o for o in (env("CSRF_TRUSTED_ORIGINS") or "").split(",") if o]

if env("STORAGE_BACKEND", "filesystem") == "s3":
    STORAGES["default"] = {  # noqa: F405
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": env("S3_ENDPOINT_URL"),
            "bucket_name": env("S3_BUCKET", "amm-documents"),
            "access_key": env("S3_ACCESS_KEY"),
            "secret_key": env("S3_SECRET_KEY"),
            "file_overwrite": False,
            "default_acl": "private",
        },
    }
