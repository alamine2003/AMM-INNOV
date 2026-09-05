"""Base settings shared by every environment. Everything is driven by environment variables."""

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import dj_database_url
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_prometheus",
    "channels",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "simple_history",
    "django_celery_beat",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.amm",
    "apps.documents",
    "apps.alerts",
    "apps.notifications",
    "apps.realtime",
    "apps.analytics",
    "apps.imports",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database, cache, channel layer, Celery
# ---------------------------------------------------------------------------
DATABASE_URL = env("DATABASE_URL", "postgres://amm:amm@localhost:5432/amm")
DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=60)}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = env("TIME_ZONE", "Africa/Dakar")
CELERY_ENABLE_UTC = True
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "recompute-all-statuses": {
        "task": "apps.amm.tasks.recompute_all_statuses",
        "schedule": crontab(hour=0, minute=5),
    },
    "evaluate-alert-rules": {
        "task": "apps.alerts.tasks.evaluate_alert_rules",
        "schedule": crontab(hour=0, minute=15),
    },
    "refresh-analytics-views": {
        "task": "apps.analytics.tasks.refresh_analytics_views",
        "schedule": crontab(hour=0, minute=30),
    },
    "send-weekly-digest": {
        "task": "apps.notifications.tasks.send_weekly_digest",
        "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
    },
    "cleanup-notifications": {
        "task": "apps.notifications.tasks.cleanup_notifications",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
    },
    "purge-archived-documents": {
        "task": "apps.documents.tasks.purge_archived_documents",
        "schedule": crontab(hour=4, minute=0, day_of_month="1", month_of_year="1"),
    },
}

# ---------------------------------------------------------------------------
# Auth, API
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {"login": "10/min"},
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "URL_FORMAT_OVERRIDE": None,  # `?format=xlsx` belongs to the export endpoint
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AMM INNOV API",
    "DESCRIPTION": "Suivi des Autorisations de Mise sur le Marché en Afrique.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_CREDENTIALS = True
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")

# ---------------------------------------------------------------------------
# Email (EMAIL_URL: console:// | smtp://user:pass@host:port?tls=1 | locmem://)
# ---------------------------------------------------------------------------


def parse_email_url(url: str) -> dict:
    parsed = urlparse(url)
    scheme = parsed.scheme or "console"
    if scheme == "console":
        return {"EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend"}
    if scheme == "locmem":
        return {"EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
    if scheme == "dummy":
        return {"EMAIL_BACKEND": "django.core.mail.backends.dummy.EmailBackend"}
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    return {
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": parsed.hostname or "localhost",
        "EMAIL_PORT": parsed.port or (465 if scheme == "smtps" else 25),
        "EMAIL_HOST_USER": unquote(parsed.username or ""),
        "EMAIL_HOST_PASSWORD": unquote(parsed.password or ""),
        "EMAIL_USE_TLS": query.get("tls", "0") in {"1", "true"},
        "EMAIL_USE_SSL": scheme == "smtps" or query.get("ssl", "0") in {"1", "true"},
    }


globals().update(parse_email_url(env("EMAIL_URL", "console://")))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "AMM INNOV <no-reply@amm.local>")

# ---------------------------------------------------------------------------
# Files, i18n, static
# ---------------------------------------------------------------------------
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
MEDIA_URL = "/media/"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DOCUMENT_MAX_MB = int(env("DOCUMENT_MAX_MB", "25"))
DOCUMENT_RETENTION_YEARS = 5
# Déluge d'alertes au premier lancement : une alerte dont l'échéance est plus ancienne que ce
# délai est créée (tableaux de bord, liste des alertes) mais ne déclenche pas de notification,
# sauf s'il s'agit de la plus récente d'une AMM encore actionnable (non expirée).
ALERTS_DISPATCH_MAX_AGE_DAYS = int(env("ALERTS_DISPATCH_MAX_AGE_DAYS", "30"))
DATA_UPLOAD_MAX_MEMORY_SIZE = DOCUMENT_MAX_MB * 1024 * 1024 + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

LANGUAGE_CODE = "fr"
TIME_ZONE = env("TIME_ZONE", "Africa/Dakar")
USE_I18N = True
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
