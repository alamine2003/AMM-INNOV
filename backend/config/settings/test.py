"""Test settings: SQLite by default, in-memory channel layer, eager Celery, fast hashing."""

import os
import tempfile

import dj_database_url

from .base import *  # noqa: F403
from .base import BASE_DIR

DEBUG = False
SECRET_KEY = "test-secret-key-long-enough-for-hmac-sha256-0123456789"
DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("DATABASE_URL_TEST")
        or os.environ.get("DATABASE_URL", "")
        or f"sqlite:///{BASE_DIR / '.test-db.sqlite3'}"
    )
}
if DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3" and not os.environ.get(
    "DATABASE_URL_TEST"
):
    # Allow running the suite against Postgres only when explicitly requested.
    DATABASES["default"] = dj_database_url.parse(f"sqlite:///{BASE_DIR / '.test-db.sqlite3'}")

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = tempfile.mkdtemp(prefix="amm-test-media-")
STATIC_ROOT = tempfile.mkdtemp(prefix="amm-test-static-")
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {  # noqa: F405
    "login": "1000/min",
    "login_email": "1000/min",
}
