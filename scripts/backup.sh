#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Sauvegarde AMM INNOV : pg_dump compressé + archive tar des médias (scans PDF),
# puis purge des sauvegardes plus anciennes que BACKUP_RETENTION_DAYS jours.
#
# Conçu pour tourner dans le service compose `backup` (image postgres:16) :
#   make backup                       (dev, à la demande)
#   service `backup` en production    (boucle quotidienne à BACKUP_HOUR)
#
# Variables : PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE (libpq),
#             BACKUP_DIR (/backups), MEDIA_DIR (/media), BACKUP_RETENTION_DAYS (30)
# Sorties  : $BACKUP_DIR/amm-db-AAAAMMJJ-HHMMSS.sql.gz
#            $BACKUP_DIR/amm-media-AAAAMMJJ-HHMMSS.tar.gz
#            $BACKUP_DIR/latest-db.sql.gz et latest-media.tar.gz (liens symboliques)
# ---------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
MEDIA_DIR="${MEDIA_DIR:-/media}"
RETENTION="${BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DB_FILE="${BACKUP_DIR}/amm-db-${STAMP}.sql.gz"
MEDIA_FILE="${BACKUP_DIR}/amm-media-${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

echo "[backup] ${STAMP} — base ${PGDATABASE:-amm}@${PGHOST:-postgres}"
pg_dump --no-owner --no-privileges --format=plain "${PGDATABASE:-amm}" | gzip -6 > "${DB_FILE}.part"
mv "${DB_FILE}.part" "${DB_FILE}"
ln -sfn "$(basename "${DB_FILE}")" "${BACKUP_DIR}/latest-db.sql.gz"
echo "[backup] base : ${DB_FILE} ($(du -h "${DB_FILE}" | cut -f1))"

if [ -d "${MEDIA_DIR}" ] && [ -n "$(ls -A "${MEDIA_DIR}" 2>/dev/null)" ]; then
  tar -czf "${MEDIA_FILE}.part" -C "${MEDIA_DIR}" .
  mv "${MEDIA_FILE}.part" "${MEDIA_FILE}"
  ln -sfn "$(basename "${MEDIA_FILE}")" "${BACKUP_DIR}/latest-media.tar.gz"
  echo "[backup] médias : ${MEDIA_FILE} ($(du -h "${MEDIA_FILE}" | cut -f1))"
else
  echo "[backup] médias : répertoire ${MEDIA_DIR} vide ou absent, archive ignorée"
fi

# Empreintes pour le contrôle d'intégrité
( cd "${BACKUP_DIR}" && sha256sum "$(basename "${DB_FILE}")" $( [ -f "${MEDIA_FILE}" ] && basename "${MEDIA_FILE}" ) >> SHA256SUMS ) || true

# Rétention
deleted=$(find "${BACKUP_DIR}" -maxdepth 1 -type f \( -name 'amm-db-*.sql.gz' -o -name 'amm-media-*.tar.gz' \) \
          -mtime "+${RETENTION}" -print -delete | wc -l)
echo "[backup] rétention ${RETENTION} j : ${deleted} fichier(s) supprimé(s)"
echo "[backup] terminé"
