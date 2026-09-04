#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Restauration AMM INNOV depuis une sauvegarde produite par backup.sh.
#
#   restore.sh /backups/amm-db-AAAAMMJJ-HHMMSS.sql.gz [/backups/amm-media-....tar.gz]
#
# À exécuter dans le service compose `backup` (make restore FILE=... [MEDIA=...]).
# La base est recréée : toutes les données actuelles sont PERDUES. Arrêter
# backend/worker/beat avant (docker compose stop backend worker beat).
# Variables : PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE, MEDIA_DIR (/media),
#             RESTORE_YES=1 pour ne pas demander de confirmation.
# ---------------------------------------------------------------------------
set -euo pipefail

DB_FILE="${1:-}"
MEDIA_FILE="${2:-}"
DB="${PGDATABASE:-amm}"
MEDIA_DIR="${MEDIA_DIR:-/media}"

if [ -z "${DB_FILE}" ] || [ ! -f "${DB_FILE}" ]; then
  echo "Usage : restore.sh <sauvegarde.sql.gz> [medias.tar.gz]" >&2
  exit 1
fi

echo "[restore] base cible : ${DB}@${PGHOST:-postgres} — source : ${DB_FILE}"
if [ "${RESTORE_YES:-}" != "1" ]; then
  read -r -p "Toutes les données de ${DB} seront remplacées. Continuer ? [oui/N] " answer
  [ "${answer}" = "oui" ] || { echo "Abandon."; exit 1; }
fi

# Déconnecte les sessions, recrée la base
psql -v ON_ERROR_STOP=1 -d postgres <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS "${DB}";
CREATE DATABASE "${DB}" OWNER "${PGUSER:-amm}";
SQL

echo "[restore] import du dump…"
gunzip -c "${DB_FILE}" | psql -v ON_ERROR_STOP=1 -q -d "${DB}"
echo "[restore] base restaurée"

if [ -n "${MEDIA_FILE}" ]; then
  [ -f "${MEDIA_FILE}" ] || { echo "Archive médias introuvable : ${MEDIA_FILE}" >&2; exit 1; }
  if [ ! -w "${MEDIA_DIR}" ]; then
    echo "[restore] ${MEDIA_DIR} n'est pas inscriptible (monté en lecture seule ?)." >&2
    echo "          Relancer avec : docker compose run --rm -v amm-innov_media:/media backup /scripts/restore.sh ..." >&2
    exit 1
  fi
  echo "[restore] extraction des médias dans ${MEDIA_DIR}…"
  tar -xzf "${MEDIA_FILE}" -C "${MEDIA_DIR}"
  echo "[restore] médias restaurés"
fi

echo "[restore] terminé. Redémarrer : docker compose up -d backend worker beat"
