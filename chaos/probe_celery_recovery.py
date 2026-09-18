"""Un même processus (comme Daphne) publie une tâche avant, pendant et après une coupure Redis."""
import sys, time, os
sys.path.insert(0, "/app"); os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")
import django; django.setup()
from apps.documents.tasks import generate_document_preview as t

def attempt(label):
    s = time.monotonic()
    try:
        t.delay("00000000-0000-0000-0000-000000000000"); r = "ok"
    except Exception as exc:
        r = f"{type(exc).__name__}: {str(exc).strip()[:70]}"
    print(f"{label:30} {time.monotonic()-s:6.2f}s {r}", flush=True)

attempt("avant coupure")
open("/tmp/ready", "w").close()
while not os.path.exists("/tmp/redis-down"): time.sleep(0.2)
attempt("pendant coupure")
while not os.path.exists("/tmp/redis-up"): time.sleep(0.2)
for i in range(3):
    attempt(f"après retour #{i+1}"); time.sleep(2)
