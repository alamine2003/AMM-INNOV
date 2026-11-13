#!/usr/bin/env bash
# Restaure une sauvegarde chiffrée d'AMM GH dans la base de ce serveur.
#
#   scripts/serveur/restaurer_base.sh amm-render-AAAAMMJJ-HHMMSS.dump.gpg
#   scripts/serveur/restaurer_base.sh amm-render-AAAAMMJJ-HHMMSS.dump.gpg --remplacer
#
# Sans --remplacer, une base qui contient déjà des données est refusée : rien n'est effacé
# par mégarde. Avec, la base est effacée puis recréée depuis la sauvegarde (bascule finale).
# La phrase secrète est demandée au clavier (ou lue dans BACKUP_PASSPHRASE) ; la copie
# déchiffrée ne sort pas du conteneur PostgreSQL et y est effacée à la fin.
set -euo pipefail

file=${1:?usage : scripts/serveur/restaurer_base.sh <sauvegarde.dump.gpg> [--remplacer]}
replace=0
[ "${2:-}" = "--remplacer" ] && replace=1
[ -s "$file" ] || { echo "[amm-gh] ERREUR : fichier absent ou vide : $file" >&2; exit 1; }
file=$(cd "$(dirname "$file")" && pwd)/$(basename "$file")
here=$(cd "$(dirname "$0")" && pwd)

log() { echo "[amm-gh] $*" >&2; }
die() { log "ERREUR : $*"; exit 1; }
compose() { "$here/compose.sh" "$@"; }
pg() { compose exec -T postgres sh -c "$1"; }
sql() { pg "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atq -c \"$1\""; }

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  IFS= read -rsp "Phrase secrète des sauvegardes : " BACKUP_PASSPHRASE; echo >&2
fi
[ -n "$BACKUP_PASSPHRASE" ] || die "phrase secrète vide"

log "arrêt de l'application (la base reste en marche)"
compose stop backend worker beat backup >/dev/null 2>&1 || true
compose up -d postgres >/dev/null 2>&1 || die "impossible de démarrer la base (scripts/serveur/compose.sh up -d postgres)"
for _ in $(seq 1 60); do
  sql "select 1" >/dev/null 2>&1 && break
  sleep 1
done
sql "select 1" >/dev/null 2>&1 || die "la base ne démarre pas"

tables=$(sql "select count(*) from information_schema.tables where table_schema = 'public'")
if [ "$tables" -gt 0 ]; then
  [ "$replace" = 1 ] || die "la base contient déjà ${tables} tables. Pour la remplacer par la sauvegarde, relancer avec --remplacer (son contenu actuel sera effacé)."
  log "effacement de la base actuelle"
  pg 'dropdb --force -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
fi

cleanup() { pg 'rm -f /tmp/backup.dump /tmp/backup.dump.gpg' >/dev/null 2>&1 || true; }
trap cleanup EXIT
compose cp "$file" postgres:/tmp/backup.dump.gpg >/dev/null 2>&1 || die "copie de la sauvegarde dans le conteneur impossible"

log "déchiffrement"
compose exec -T postgres gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 \
  --output /tmp/backup.dump --decrypt /tmp/backup.dump.gpg <<< "$BACKUP_PASSPHRASE" \
  || die "déchiffrement impossible : phrase secrète incorrecte ou fichier abîmé"

log "restauration"
pg 'pg_restore --no-owner --no-acl --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/backup.dump' \
  || die "pg_restore a échoué"

tables=$(sql "select count(*) from information_schema.tables where table_schema = 'public'")
for table in amm_marketingauthorization catalog_product accounts_user; do
  [ "$(sql "select exists (select 1 from ${table})")" = "t" ] || die "table ${table} vide après restauration"
done
log "OK : $(basename "$file") restaurée (${tables} tables). Relancer l'application : scripts/serveur/compose.sh up -d"
