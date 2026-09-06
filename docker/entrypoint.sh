#!/usr/bin/env bash
# Point d'entrée du conteneur backend.
#  1. attend PostgreSQL et Redis (scripts/wait-for.py, embarqué dans l'image) ;
#  2. applique les migrations et collecte les fichiers statiques (désactivable
#     avec RUN_MIGRATIONS=0 / COLLECT_STATIC=0, ce que font worker et beat) ;
#  3. exécute la commande passée (Daphne par défaut, ou celery worker/beat).
set -euo pipefail

: "${DATABASE_URL:=postgres://amm:amm@postgres:5432/amm}"
: "${REDIS_URL:=redis://redis:6379/0}"
: "${RUN_MIGRATIONS:=1}"
: "${COLLECT_STATIC:=1}"
: "${WAIT_TIMEOUT:=120}"

echo "[entrypoint] attente des dépendances (timeout ${WAIT_TIMEOUT}s)…"
python /usr/local/bin/wait-for.py --timeout "${WAIT_TIMEOUT}" "${DATABASE_URL}" "${REDIS_URL}"

if [ "${RUN_MIGRATIONS}" = "1" ]; then
  echo "[entrypoint] python manage.py migrate --noinput"
  python manage.py migrate --noinput
elif [ "${WAIT_FOR_MIGRATIONS:-1}" = "1" ]; then
  # worker et beat démarrent en même temps que le web : attendre ses migrations (1er déploiement)
  echo "[entrypoint] attente des migrations (timeout ${WAIT_TIMEOUT}s)…"
  waited=0
  until python manage.py migrate --check >/dev/null 2>&1; do
    waited=$((waited + 5))
    if [ "${waited}" -ge "${WAIT_TIMEOUT}" ]; then
      echo "[entrypoint] migrations toujours absentes après ${WAIT_TIMEOUT}s, démarrage quand même"
      break
    fi
    sleep 5
  done
fi

# Premier compte administrateur (plateformes sans shell : Railway, Render) : créé une seule fois
# si DJANGO_SUPERUSER_EMAIL et DJANGO_SUPERUSER_PASSWORD sont définis, ignoré s'il existe déjà.
if [ "${RUN_MIGRATIONS}" = "1" ] && [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  echo "[entrypoint] createsuperuser ${DJANGO_SUPERUSER_EMAIL} (ignoré s'il existe)"
  python manage.py createsuperuser --noinput --email "${DJANGO_SUPERUSER_EMAIL}" 2>/dev/null \
    || echo "[entrypoint] compte déjà présent, inchangé"
fi

if [ "${COLLECT_STATIC}" = "1" ]; then
  echo "[entrypoint] python manage.py collectstatic --noinput"
  python manage.py collectstatic --noinput
fi

# `serve` : serveur ASGI. WEB_CONCURRENCY=1 -> Daphne (un processus, dev) ;
# WEB_CONCURRENCY>1 -> uvicorn avec N workers (production : ~80 req/s par worker mesurés).
# PORT est imposé par la plateforme (Railway, Render) ; BIND_HOST=:: pour le réseau privé IPv6 de Railway.
if [ "${1:-}" = "serve" ] && [ "${AMM_ROLE:-web}" = "worker" ]; then
  # Railway : même image et même railway.json pour le web et le worker, rôle par variable.
  echo "[entrypoint] worker Celery (beat intégré), concurrence ${CELERY_CONCURRENCY:-2}"
  exec celery -A config worker -l info --concurrency "${CELERY_CONCURRENCY:-2}" \
    -B --scheduler django_celery_beat.schedulers:DatabaseScheduler
fi

if [ "${1:-}" = "serve" ]; then
  : "${WEB_CONCURRENCY:=1}"
  : "${PORT:=8000}"
  : "${BIND_HOST:=0.0.0.0}"
  if [ "${WEB_CONCURRENCY}" -gt 1 ]; then
    echo "[entrypoint] uvicorn, ${WEB_CONCURRENCY} workers, ${BIND_HOST}:${PORT}"
    exec uvicorn config.asgi:application --host "${BIND_HOST}" --port "${PORT}" \
      --workers "${WEB_CONCURRENCY}" --proxy-headers --forwarded-allow-ips='*' --no-access-log
  fi
  echo "[entrypoint] daphne, ${BIND_HOST}:${PORT}"
  exec daphne -b "${BIND_HOST}" -p "${PORT}" config.asgi:application
fi

echo "[entrypoint] exec: $*"
exec "$@"
