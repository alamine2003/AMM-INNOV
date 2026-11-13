#!/usr/bin/env bash
# Restauration d'essai d'une sauvegarde chiffrée d'AMM GH : la preuve qu'elle se relit.
#
#   scripts/verify_backup.sh amm-render-AAAAMMJJ-HHMMSS.dump.gpg
#
# Le fichier est déchiffré puis restauré dans une base PostgreSQL jetable (conteneur Docker,
# supprimé à la fin), et son contenu est contrôlé : tables, migrations, fiches AMM, produits,
# comptes. Rien n'est écrit ailleurs : ni la base de production, ni le disque (la copie
# déchiffrée reste dans le conteneur).
#
# Phrase secrète : variable BACKUP_PASSPHRASE (workflow « Base Render », chaque nuit), sinon
# demandée au clavier (essai sur un poste : elle n'est ni affichée ni enregistrée).
# Outil : Docker seulement (gpg, pg_restore et psql sont ceux de l'image postgres).
set -euo pipefail

file=${1:?usage : scripts/verify_backup.sh <sauvegarde.dump.gpg>}
[ -s "$file" ] || { echo "[verify-backup] ERREUR : fichier absent ou vide : $file" >&2; exit 1; }

image="postgres:${PG_VERSION:-18}"
name="amm-restore-test-$$"
log() { echo "[verify-backup] $*" >&2; }
die() { log "ERREUR : $*"; exit 1; }
cleanup() { docker rm -f -v "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
  IFS= read -rsp "Phrase secrète des sauvegardes : " BACKUP_PASSPHRASE; echo >&2
fi
[ -n "$BACKUP_PASSPHRASE" ] || die "phrase secrète vide"

log "base jetable ${image}"
docker run -d --name "$name" -e POSTGRES_PASSWORD=essai -e POSTGRES_DB=amm "$image" >/dev/null
docker cp "$file" "$name:/tmp/backup.dump.gpg"
# Par TCP : pendant l'initialisation, le serveur n'écoute que sur son socket local.
sql() { docker exec -e PGPASSWORD=essai "$name" psql -h 127.0.0.1 -U postgres -d amm -Atq -c "$1"; }
for _ in $(seq 1 60); do
  sql "select 1" >/dev/null 2>&1 && break
  sleep 1
done
sql "select 1" >/dev/null 2>&1 || die "la base jetable ne démarre pas"

log "déchiffrement"
docker exec -i "$name" gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 0 \
  --output /tmp/backup.dump --decrypt /tmp/backup.dump.gpg <<< "$BACKUP_PASSPHRASE" \
  || die "déchiffrement impossible : phrase secrète incorrecte ou fichier abîmé"

log "restauration"
docker exec -e PGPASSWORD=essai "$name" pg_restore --no-owner --no-acl --exit-on-error \
  -h 127.0.0.1 -U postgres -d amm /tmp/backup.dump \
  || die "pg_restore a échoué : la sauvegarde ne se restaure pas"

tables=$(sql "select count(*) from information_schema.tables where table_schema = 'public'")
migrations=$(sql "select count(*) from django_migrations")
[ "$tables" -gt 0 ] && [ "$migrations" -gt 0 ] || die "base restaurée vide"
# Présence seulement : le journal du workflow est public, aucun chiffre métier n'y figure.
for table in amm_marketingauthorization catalog_product catalog_country accounts_user; do
  [ "$(sql "select exists (select 1 from ${table})")" = "t" ] || die "table ${table} vide"
done

log "OK : $(basename "$file") se déchiffre et se restaure (${tables} tables, ${migrations} migrations ;" \
  "fiches AMM, produits, pays et comptes présents)"
