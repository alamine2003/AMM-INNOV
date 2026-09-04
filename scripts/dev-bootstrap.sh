#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Amorçage complet de l'environnement de développement :
#   .env → docker compose up → migrations → données de démo → import du
#   classeur Excel s'il est présent dans data/raw/.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose}"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "[bootstrap] .env créé depuis .env.example"
fi

echo "[bootstrap] démarrage de la stack…"
${COMPOSE} up -d --build

echo "[bootstrap] attente du backend…"
for i in $(seq 1 60); do
  # L'API répond 200 sur sa sonde de santé (base + Redis)
  if ${COMPOSE} exec -T backend curl -fsS -o /dev/null --max-time 3 http://localhost:8000/api/v1/health 2>/dev/null; then
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then echo "[bootstrap] le backend ne répond pas, consulter : make logs SERVICE=backend" >&2; exit 1; fi
done

echo "[bootstrap] migrations…"
${COMPOSE} exec -T backend python manage.py migrate --noinput

echo "[bootstrap] données de démonstration…"
${COMPOSE} exec -T backend python manage.py seed_demo

shopt -s nullglob
workbooks=(data/raw/*.xlsx)
if [ ${#workbooks[@]} -gt 0 ]; then
  wb="${workbooks[0]}"
  echo "[bootstrap] import du classeur ${wb}…"
  ${COMPOSE} cp "${wb}" backend:/tmp/import.xlsx
  ${COMPOSE} exec -T backend python manage.py import_excel /tmp/import.xlsx ${IMPORT_TODAY:+--today "${IMPORT_TODAY}"}
else
  echo "[bootstrap] aucun classeur dans data/raw/ (déposer le .xlsx puis : make import FILE=data/raw/<fichier>.xlsx)"
fi

cat <<MSG

[bootstrap] prêt.
  Application : http://localhost:${FRONTEND_PORT:-5173}
  API docs    : http://localhost:${BACKEND_PORT:-8000}/api/docs
  Grafana     : http://localhost:${GRAFANA_PORT:-3000}  (admin / admin)
  Mailpit     : http://localhost:${MAILPIT_HTTP_PORT:-8025}
  Comptes     : ceo@amm.local, siege@amm.local, senegal@amm.local — mot de passe Passw0rd!
MSG
