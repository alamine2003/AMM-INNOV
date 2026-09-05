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
fi

if [ "${COLLECT_STATIC}" = "1" ]; then
  echo "[entrypoint] python manage.py collectstatic --noinput"
  python manage.py collectstatic --noinput
fi

# `serve` : serveur ASGI. WEB_CONCURRENCY=1 -> Daphne (un processus, dev) ;
# WEB_CONCURRENCY>1 -> uvicorn avec N workers (production : ~80 req/s par worker mesurés).
if [ "${1:-}" = "serve" ]; then
  : "${WEB_CONCURRENCY:=1}"
  if [ "${WEB_CONCURRENCY}" -gt 1 ]; then
    echo "[entrypoint] uvicorn, ${WEB_CONCURRENCY} workers"
    exec uvicorn config.asgi:application --host 0.0.0.0 --port 8000 \
      --workers "${WEB_CONCURRENCY}" --proxy-headers --forwarded-allow-ips='*' --no-access-log
  fi
  echo "[entrypoint] daphne"
  exec daphne -b 0.0.0.0 -p 8000 config.asgi:application
fi

echo "[entrypoint] exec: $*"
exec "$@"
