"""Chronomètre chaque usage de Redis par l'application quand Redis est coupé ou figé."""
import sys, time
sys.path.insert(0, "/app")
import os; os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
import django; django.setup()
from django.conf import settings

def timed(label, fn):
    t = time.monotonic()
    try:
        fn(); outcome = "ok"
    except Exception as exc:
        outcome = f"{type(exc).__name__}: {str(exc)[:80]}"
    print(f"{label:28} {time.monotonic()-t:7.2f}s  {outcome}", flush=True)

from apps.realtime.publisher import publish
from django.core.cache import cache
import redis
from apps.documents.tasks import generate_document_preview
from apps.core import metrics
timed("realtime.publish", lambda: publish("global", {"type": "x"}))
timed("cache.get (throttle login)", lambda: cache.get("k"))
timed("health redis ping", lambda: redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1).ping())
timed("metrics.ws_connected", metrics.ws_connected)
timed("celery task.delay", lambda: generate_document_preview.delay("00000000-0000-0000-0000-000000000000"))
