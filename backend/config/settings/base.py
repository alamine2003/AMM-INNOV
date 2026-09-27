"""Base settings shared by every environment. Everything is driven by environment variables."""

import os
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import dj_database_url
from celery.schedules import crontab

from config.sentry import init_sentry

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def env(name: str, default: str | None = None) -> str | None:
    """Variable d'environnement sans espaces ni retour à la ligne autour.

    Une valeur collée dans le tableau de bord de l'hébergeur garde souvent un « \\n » final :
    « https://….r2.cloudflarestorage.com\\n » rend l'URL invalide pour boto3 (erreur 500 à
    l'envoi des scans).
    """
    value = os.environ.get(name)
    return default if value is None else value.strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


_APP_VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}")


def clean_app_version(raw: str | None) -> str:
    """Version publique de /api/v1/health : lettres, chiffres et . _ + -, 64 caractères au plus.

    Vide ou non conforme → « dev ». `env("APP_VERSION", "dev")` ne suffit pas : docker compose
    transmet une chaîne vide pour la ligne `APP_VERSION=` de .env.
    """
    value = (raw or "").strip()
    return value if _APP_VERSION_RE.fullmatch(value) else "dev"


APP_VERSION = clean_app_version(env("APP_VERSION"))

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
    "apps.core.observability.RequestContextMiddleware",
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
# Pool de connexions psycopg (Django 5.1) sur PostgreSQL. Sous ASGI, chaque requête tourne dans
# un nouveau thread : sans pool, chaque thread ouvrait sa propre connexion et PostgreSQL
# saturait (« too many clients ») dès 30 utilisateurs simultanés. Avec le pool, les requêtes
# en excès attendent une connexion libre (DB_POOL_TIMEOUT) au lieu d'échouer.
DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=0)}
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
    _db_options = DATABASES["default"].setdefault("OPTIONS", {})
    # Délais bornés (campagne de chaos s02b/s02c) : sans eux, une base figée ou une requête
    # emballée retenait la requête HTTP jusqu'au délai de nginx (120 s) et une transaction
    # abandonnée gardait ses verrous. statement_timeout se relève pour le worker
    # (DB_STATEMENT_TIMEOUT_MS) si un traitement de masse le demande.
    _db_options["connect_timeout"] = int(env("DB_CONNECT_TIMEOUT", "5"))
    _db_options["options"] = " ".join(
        f"-c {name}={env(var, default)}"
        for name, var, default in (
            ("statement_timeout", "DB_STATEMENT_TIMEOUT_MS", "30000"),
            ("lock_timeout", "DB_LOCK_TIMEOUT_MS", "10000"),
            ("idle_in_transaction_session_timeout", "DB_IDLE_TX_TIMEOUT_MS", "60000"),
        )
    )
    if env_bool("DB_POOL", True):
        _db_options["pool"] = {
            "min_size": int(env("DB_POOL_MIN_SIZE", "1")),
            "max_size": int(env("DB_POOL_MAX_SIZE", "20")),
            "timeout": float(env("DB_POOL_TIMEOUT", "10")),
        }
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("REDIS_URL", "redis://localhost:6379/0")
# Redis ne sert qu'à des fonctions accessoires à la requête (temps réel, throttle, file des
# tâches) : ses appels doivent échouer vite. redis-py attend 5 s par défaut ; mesuré en
# laboratoire (s03, s04), une écriture d'AMM payait ce délai trois fois, connexion PostgreSQL
# tenue. Voir aussi apps/core/resilience.py (disjoncteur).
REDIS_CONNECT_TIMEOUT = float(env("REDIS_CONNECT_TIMEOUT", "1"))
REDIS_SOCKET_TIMEOUT = float(env("REDIS_SOCKET_TIMEOUT", "1"))

# Cache partagé entre les processus web : throttles de connexion et futurs caches applicatifs.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "socket_connect_timeout": REDIS_CONNECT_TIMEOUT,
            "socket_timeout": REDIS_SOCKET_TIMEOUT,
        },
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [
                {
                    "address": REDIS_URL,
                    "socket_connect_timeout": REDIS_CONNECT_TIMEOUT,
                    # La réception WebSocket attend 5 s en BZPOPMIN (channels_redis) : un délai
                    # socket de 5 s (défaut redis-py) ou moins la couperait. La publication, elle,
                    # est bornée à part (apps/realtime/publisher.py).
                    "socket_timeout": 8,
                }
            ]
        },
    }
}

CELERY_BROKER_URL = REDIS_URL
# Aucun code ne lit les résultats des tâches. Le backend de résultats Redis abonnait chaque
# processus web au pub/sub des résultats : Redis figé, `delay()` ne rendait plus la main (s03b).
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_connect_timeout": REDIS_CONNECT_TIMEOUT,
    "socket_timeout": 3,  # au-dessus du BRPOP d'une seconde du worker
    # doit dépasser la plus longue tâche (analyse de dossier : 21 min) et la plus longue
    # relance différée (e-mails : 10 min), sinon la tâche serait redistribuée en double
    "visibility_timeout": 3600,
}
# Publication d'une tâche depuis une requête : un essai de plus, pas quatre (19 s mesurées).
CELERY_TASK_PUBLISH_RETRY_POLICY = {
    "max_retries": 1,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 0.5,
}
# Worker tué en cours de tâche (s12b) : la tâche était déjà acquittée, donc perdue. Acquittée
# après exécution, elle est redistribuée ; les tâches sont idempotentes (voir chaque tâche).
# Un seul worker dans le conteneur du web (Render gratuit, AMM_ROLE=all) : au démarrage, une
# analyse restée « en cours » a forcément été coupée (mise en veille, mémoire) et reprend tout
# de suite. Désactivé par défaut avec plusieurs workers (un redémarrage couperait les autres).
WORKER_RESUME_INTERRUPTED = env_bool("WORKER_RESUME_INTERRUPTED", env("AMM_ROLE", "") == "all")
# Render gratuit endort le service après 15 min sans requête entrante, worker compris, même en
# pleine analyse. Tant qu'il reste du travail, le worker appelle cette adresse publique toutes
# les KEEPALIVE_SECONDS (RENDER_EXTERNAL_URL est fournie par Render). Vide : désactivé.
KEEPALIVE_URL = env(
    "KEEPALIVE_URL",
    f"{env('RENDER_EXTERNAL_URL')}/api/v1/health/live" if env("RENDER_EXTERNAL_URL") else "",
)
KEEPALIVE_SECONDS = int(env("KEEPALIVE_SECONDS", "240"))
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
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
    # Règle 4 : rappel quotidien de chaque AMM « À renouveler » (après le recalcul de 00:05).
    "send-renewal-reminders": {
        "task": "apps.notifications.tasks.send_renewal_reminders",
        "schedule": crontab(hour=7, minute=30),
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
    # Rattrapage : e-mails non partis, analyses bloquées, aperçus manquants (tâches perdues
    # quand Redis ou le worker sont tombés). La base est la source de vérité du travail restant.
    "recover-pending-work": {
        "task": "apps.core.tasks.recover_pending_work",
        "schedule": crontab(minute="*/5"),
    },
    "check-integrity": {
        "task": "apps.core.tasks.check_integrity",
        "schedule": crontab(hour=5, minute=0),
    },
}

# ---------------------------------------------------------------------------
# Auth, API
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
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
    "EXCEPTION_HANDLER": "apps.core.exceptions.exception_handler",
    # Anti force brute : par adresse IP (un bureau derrière un NAT compte pour une IP) et par
    # compte visé (plusieurs IP sur un même email). Derrière un proxy, NUM_PROXIES (prod) permet
    # de lire la vraie IP cliente dans X-Forwarded-For.
    "DEFAULT_THROTTLE_RATES": {"login": "30/min", "login_email": "10/min"},
    "NUM_PROXIES": int(env("NUM_PROXIES", "0")) or None,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "URL_FORMAT_OVERRIDE": None,  # `?format=xlsx` belongs to the export endpoint
}

from datetime import timedelta  # noqa: E402

# Refresh token JWT en cookie httpOnly (jamais lisible par du JavaScript) sur le seul chemin
# /api/v1/auth. SameSite=Lax suffit quand frontend et API partagent le même site (app.X / api.X) ;
# entre deux domaines sans lien (*.netlify.app / *.up.railway.app) il faut SameSite=None + Secure,
# que Safari bloque : prévoir un domaine commun (docs/deploiement-netlify-railway.md).
AUTH_REFRESH_COOKIE = {
    "name": env("AUTH_REFRESH_COOKIE_NAME", "amm_refresh"),
    "secure": env_bool("AUTH_REFRESH_COOKIE_SECURE", not DEBUG),
    "samesite": env("AUTH_REFRESH_COOKIE_SAMESITE", "Lax"),
    "domain": env("AUTH_REFRESH_COOKIE_DOMAIN") or None,
    "path": "/api/v1/auth",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    # PRD US1.1 : la session expire après 12 h d'inactivité. Le refresh est renouvelé à chaque
    # rafraîchissement (rotation), donc 12 h glissantes tant que l'utilisateur est actif.
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=12),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AMM GH API",
    "DESCRIPTION": "Suivi des Autorisations de Mise sur le Marché en Afrique.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Documentation réservée aux utilisateurs connectés : session (/admin) ou JWT.
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    "SERVE_AUTHENTICATION": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "COMPONENT_SPLIT_REQUEST": True,
    # Noms stables pour les enums partagés (sinon « Status1d1Enum », qui change à chaque ajout).
    "ENUM_NAME_OVERRIDES": {
        "AmmStatusEnum": "apps.amm.models.MarketingAuthorization.Status",
        "UrgencyEnum": "apps.amm.models.MarketingAuthorization.Urgency",
        "DossierStateEnum": "apps.amm.models.MarketingAuthorization.DossierState",
        "WorkflowStatusEnum": "apps.amm.models.Renewal.WorkflowStatus",
        "AlertStatusEnum": "apps.alerts.models.Alert.Status",
        "AlertResolutionEnum": "apps.alerts.models.Alert.Resolution",
        "SeverityEnum": "apps.alerts.models.AlertRule.Severity",
        "ChannelEnum": "apps.alerts.models.AlertRule.Channel",
        "DocumentKindEnum": "apps.documents.models.Document.Kind",
        "RoleEnum": "apps.accounts.models.User.Role",
        "HealthStatusEnum": "apps.accounts.serializers.HealthStatus",
        "ImportStatusEnum": "apps.imports.models.ImportBatch.Status",
        "ImportOutcomeEnum": "apps.imports.models.ImportRow.Outcome",
        "RangeCodeEnum": "apps.catalog.models.ProductRange.Code",
    },
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
CORS_ALLOW_CREDENTIALS = True
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")

# ---------------------------------------------------------------------------
# Email (EMAIL_URL : console:// | locmem:// | dummy://
#   smtp+tls://utilisateur:motdepasse@smtp.gmail.com:587   STARTTLS (recommandé)
#   smtps://utilisateur:motdepasse@smtp.example.com:465    TLS direct
#   gmail://                                               API Gmail en HTTPS (GMAIL_* ci-dessous)
#   Le mot de passe doit être encodé si besoin (@ -> %40, : -> %3A).
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
    if scheme in {"gmail", "gmail+api"}:
        # API Gmail en HTTPS : seule voie possible là où les ports SMTP sortants sont bloqués
        # (Railway). Identifiants dans GMAIL_CLIENT_ID / _SECRET / _REFRESH_TOKEN.
        return {"EMAIL_BACKEND": "apps.notifications.backends.GmailApiBackend"}
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    def flag(name: str, default: bool) -> bool:
        value = query.get(name)
        return value.strip().lower() in {"1", "true", "yes", "on"} if value else default

    # Le schéma porte le chiffrement : `smtp+tls` (STARTTLS, port 587) ou `smtps` (TLS direct,
    # port 465) ; `?tls=` et `?ssl=` restent acceptés pour forcer l'un ou l'autre.
    use_ssl = flag("ssl", scheme in {"smtps", "smtp+ssl"})
    use_tls = False if use_ssl else flag("tls", scheme in {"smtp+tls", "smtp+starttls"})
    return {
        "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "EMAIL_HOST": parsed.hostname or "localhost",
        "EMAIL_PORT": parsed.port or (465 if use_ssl else 587 if use_tls else 25),
        "EMAIL_HOST_USER": unquote(parsed.username or ""),
        "EMAIL_HOST_PASSWORD": unquote(parsed.password or ""),
        "EMAIL_USE_TLS": use_tls,
        "EMAIL_USE_SSL": use_ssl,
        # Sans délai maximal, un SMTP muet bloquerait le worker Celery indéfiniment.
        "EMAIL_TIMEOUT": int(query.get("timeout", "15")),
    }


globals().update(parse_email_url(env("EMAIL_URL", "console://")))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "AMM GH <no-reply@amm.local>")

# API Gmail (EMAIL_URL=gmail://) : jeton de rafraîchissement OAuth2, portée gmail.send.
# Obtention : python -m scripts.gmail_oauth (voir docs/deploiement-netlify-railway.md).
GMAIL_CLIENT_ID = env("GMAIL_CLIENT_ID", "")
GMAIL_CLIENT_SECRET = env("GMAIL_CLIENT_SECRET", "")
GMAIL_REFRESH_TOKEN = env("GMAIL_REFRESH_TOKEN", "")

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
# Scans PDF : "local" (MEDIA_ROOT, volume Docker) ou "s3" (MinIO en dev, R2/B2/S3 en production).
# Sur Railway (ou Render), "s3" est obligatoire : le service web et le worker n'ont pas de
# disque commun.
DOCUMENT_STORAGE = env("DOCUMENT_STORAGE") or env("STORAGE_BACKEND") or "local"
if DOCUMENT_STORAGE == "s3":
    from botocore.config import Config as _BotoConfig

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            # boto3 >= 1.36 ajoute des sommes de contrôle CRC en flux que Cloudflare R2 et
            # MinIO ne gèrent pas toutes : on ne les calcule que lorsque l'API l'exige.
            "client_config": _BotoConfig(
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                s3={"addressing_style": env("S3_ADDRESSING_STYLE", "path")},
                # défauts boto : 60 s de connexion et de lecture, relances « legacy » (s10b)
                connect_timeout=float(env("S3_CONNECT_TIMEOUT", "3")),
                read_timeout=float(env("S3_READ_TIMEOUT", "10")),
                retries={"max_attempts": 2, "mode": "standard"},
            ),
            "endpoint_url": env("S3_ENDPOINT_URL") or env("AWS_S3_ENDPOINT_URL"),
            "bucket_name": env("S3_BUCKET") or env("AWS_STORAGE_BUCKET_NAME") or "amm-documents",
            "access_key": env("S3_ACCESS_KEY") or env("AWS_ACCESS_KEY_ID"),
            "secret_key": env("S3_SECRET_KEY") or env("AWS_SECRET_ACCESS_KEY"),
            "region_name": env("S3_REGION", "auto"),
            "file_overwrite": False,
            # Scan lu depuis S3 : en mémoire jusqu'à 5 Mo, sur disque au-delà. Le défaut (0)
            # gardait tout le fichier en mémoire du processus web pendant le téléchargement.
            "max_memory_size": 5 * 1024 * 1024,
            # Téléchargement S3 séquentiel : par défaut, boto3 tire chaque scan en parts de 8 Mo
            # sur 10 fils, en mémoire. Mesuré (s08) : 8 archives simultanées portaient le
            # processus web à 641 Mio de mémoire anonyme, et 755 Mio après trois séries.
            "use_threads": False,
            "default_acl": None,
            "signature_version": "s3v4",
        },
    }
DOCUMENT_MAX_MB = int(env("DOCUMENT_MAX_MB", "25"))
DOSSIER_MAX_FILES = int(env("DOSSIER_MAX_FILES", "200"))
DOSSIER_MAX_MB = int(env("DOSSIER_MAX_MB", "250"))
DOSSIER_MAX_PAGES = int(env("DOSSIER_MAX_PAGES", "100"))
DOSSIER_MAX_IMAGE_PIXELS = int(env("DOSSIER_MAX_IMAGE_PIXELS", "40000000"))
DOSSIER_CLAMAV_COMMAND = env("DOSSIER_CLAMAV_COMMAND", "")
DOSSIER_REQUIRE_ANTIVIRUS = env_bool("DOSSIER_REQUIRE_ANTIVIRUS", False)
DOSSIER_CLAMAV_TIMEOUT = int(env("DOSSIER_CLAMAV_TIMEOUT", "60"))
# Rangement automatique d'un dossier dès que son AMM (produit + pays) est identifiée : aucune
# valeur enregistrée n'est remplacée, les écarts deviennent des « points à vérifier plus tard ».
DOSSIER_AUTO_APPLY = env_bool("DOSSIER_AUTO_APPLY", True)
# AMM absente de la base (produit hors Excel) mais décision d'origine lisible (produit, pays,
# numéro, date) : la fiche est créée d'office depuis le dossier, le siège est notifié.
DOSSIER_AUTO_CREATE = env_bool("DOSSIER_AUTO_CREATE", True)
# Classement autonome : l'application tranche seule les doutes (pays ou produits mêlés, nom
# proche, produit absent, décision illisible) et la décision officielle corrige la fiche en cas
# d'écart ; tout est listé dans le récapitulatif des imports, seuls les vrais blocages restent.
DOSSIER_AUTONOMOUS = env_bool("DOSSIER_AUTONOMOUS", True)
# Multipart file bodies stream to temporary files; only metadata counts toward memory limit.
DATA_UPLOAD_MAX_NUMBER_FILES = DOSSIER_MAX_FILES
DOCUMENT_RETENTION_YEARS = 5
# /metrics (Prometheus) : public si vide, sinon exige `Authorization: Bearer <METRICS_TOKEN>`.
METRICS_TOKEN = env("METRICS_TOKEN", "")
# Déluge d'alertes au premier lancement : une alerte dont l'échéance est plus ancienne que ce
# délai est créée (tableaux de bord, liste des alertes) mais ne déclenche pas de notification,
# sauf s'il s'agit de la plus récente d'une AMM encore actionnable (non expirée).
ALERTS_DISPATCH_MAX_AGE_DAYS = int(env("ALERTS_DISPATCH_MAX_AGE_DAYS", "30"))
# Rappel quotidien « À renouveler » : canaux utilisés (IN_APP, EMAIL), comme les canaux d'une
# règle d'alerte. Mettre « IN_APP » seul pour couper l'e-mail quotidien.
RENEWAL_REMINDER_CHANNELS = env_list("RENEWAL_REMINDER_CHANNELS", "IN_APP,EMAIL")
DATA_UPLOAD_MAX_MEMORY_SIZE = DOCUMENT_MAX_MB * 1024 * 1024 + 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

LANGUAGE_CODE = "fr"
TIME_ZONE = env("TIME_ZONE", "Africa/Dakar")
USE_I18N = True
USE_TZ = True

# Journaux JSON en production (une ligne par événement, avec l'identifiant de requête),
# texte lisible en développement. Voir apps/core/observability.py.
# Sentry : surveillance des erreurs du web et du worker, inactive tant que SENTRY_DSN est vide.
# Aucune donnée personnelle n'est envoyée (voir config/sentry.py) ; les traces de performance sont
# désactivées par défaut, les latences venant déjà des journaux JSON et de Prometheus.
SENTRY_DSN = env("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT", "dev" if DEBUG else "production")
SENTRY_RELEASE = env("SENTRY_RELEASE", "")
SENTRY_TRACES_SAMPLE_RATE = float(env("SENTRY_TRACES_SAMPLE_RATE", "0") or 0)
SENTRY_ENABLED = init_sentry(
    SENTRY_DSN,
    environment=SENTRY_ENVIRONMENT,
    release=SENTRY_RELEASE,
    traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
)

LOG_FORMAT = env("LOG_FORMAT", "text" if DEBUG else "json")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "apps.core.observability.RequestIdFilter"}},
    "formatters": {
        "text": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
        "json": {"()": "apps.core.observability.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "text",
            "filters": ["request_id"],
        }
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
# Le worker garde ce format au lieu du sien : mêmes champs dans les journaux web et Celery.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
