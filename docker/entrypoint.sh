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
  # Un port TCP ouvert ne prouve pas que la base répond (proxy, pooler, plateforme) : on
  # retente la migration sur place plutôt que de sortir. Sortir faisait boucler le conteneur
  # en redémarrages, avec une nouvelle IP à chaque fois (campagne de chaos s16).
  # Délais applicatifs levés pour la migration (0 = aucun) : elle peut attendre un verrou tenu
  # par la version encore en service, ou durer plus de 30 s sur une reprise de données.
  echo "[entrypoint] python manage.py migrate --noinput"
  waited=0
  until DB_STATEMENT_TIMEOUT_MS=0 DB_LOCK_TIMEOUT_MS=0 python manage.py migrate --noinput; do
    waited=$((waited + 5))
    if [ "${waited}" -ge "${WAIT_TIMEOUT}" ]; then
      echo "[entrypoint] base toujours indisponible après ${WAIT_TIMEOUT}s, abandon"
      exit 1
    fi
    echo "[entrypoint] base pas prête, nouvel essai dans 5 s"
    sleep 5
  done
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

# `serve` : serveur ASGI uvicorn, WEB_CONCURRENCY processus (production : ~80 req/s par worker).
# Plus de Daphne, même pour un seul processus : sur SIGTERM (redéploiement, docker stop), Daphne
# coupait les requêtes en vol (18/20 en 502) puis restait vivant sans écouter, conteneur
# « running » et jamais redémarré (campagne de chaos s11a). uvicorn draine les requêtes en vol
# pendant GRACEFUL_TIMEOUT secondes puis se termine.
# PORT est imposé par la plateforme (Railway, Render) ; BIND_HOST=:: pour le réseau privé IPv6 de Railway.
if [ "${1:-}" = "serve" ] && [ "${AMM_ROLE:-web}" = "worker" ]; then
  # Worker séparé (compose, plateforme payante) : même image, rôle par variable.
  echo "[entrypoint] worker Celery (beat intégré), concurrence ${CELERY_CONCURRENCY:-2}"
  exec celery -A config worker -l info --concurrency "${CELERY_CONCURRENCY:-2}" \
    -B --scheduler django_celery_beat.schedulers:DatabaseScheduler
fi

# Render gratuit : pas d'offre gratuite pour un worker séparé. AMM_ROLE=all lance Celery (beat
# intégré, une seule concurrence) en arrière-plan dans le même conteneur que le serveur web.
# Mémoire limitée à 512 Mo : pool « solo » (la tâche tourne dans le processus du worker, sans
# processus enfant de plus, ~100 Mo gagnés), pas d'échanges inter-workers, et moins d'arènes
# malloc. En prefork, l'analyse des 40 produits d'un dossier pays dépassait 512 Mo (instance
# tuée « Ran out of memory », 24/09/2026).
if [ "${1:-}" = "serve" ] && [ "${AMM_ROLE:-web}" = "all" ]; then
  export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
  echo "[entrypoint] worker Celery en arrière-plan (pool solo, beat intégré)"
  celery -A config worker -l info --pool solo --without-gossip --without-mingle \
    --without-heartbeat -B --scheduler django_celery_beat.schedulers:DatabaseScheduler &
fi

if [ "${1:-}" = "serve" ]; then
  : "${WEB_CONCURRENCY:=1}"
  : "${PORT:=8000}"
  : "${BIND_HOST:=0.0.0.0}"
  : "${GRACEFUL_TIMEOUT:=20}"
  echo "[entrypoint] uvicorn, ${WEB_CONCURRENCY} worker(s), ${BIND_HOST}:${PORT}"
  # --no-access-log : le journal d'accès (JSON, avec identifiant de requête) est écrit par Django
  exec uvicorn config.asgi:application --host "${BIND_HOST}" --port "${PORT}" \
    --workers "${WEB_CONCURRENCY}" --proxy-headers --forwarded-allow-ips='*' --no-access-log \
    --timeout-graceful-shutdown "${GRACEFUL_TIMEOUT}"
fi

echo "[entrypoint] exec: $*"
exec "$@"
