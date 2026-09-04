"""Development settings."""

from .base import *  # noqa: F403
from .base import env_bool

DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True
