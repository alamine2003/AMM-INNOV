#!/usr/bin/env bash
# Sauvegarde chiffrée et vérifiée de la base d'AMM GH sur son serveur (palier 1.3.0).
#
# Tourne dans le service `backup` (image postgres : pg_dump, gpg et psql y sont), chaque nuit à
# BACKUP_HOUR, ou à la demande :
#   scripts/serveur/compose.sh exec backup /scripts/serveur/sauvegarder.sh
#
# 1. pg_dump de la base, chiffré au vol (gpg AES256, BACKUP_PASSPHRASE) : aucune copie en clair
#    n'est écrite sur le disque. Sans phrase secrète, la sauvegarde est refusée.
# 2. Essai de restauration : le fichier chiffré est relu et restauré dans une base d'essai, à
#    côté de la vraie, puis contrôlé (tables, migrations, fiches AMM, produits, pays, comptes).
#    La base d'essai est supprimée à la fin. Une sauvegarde qui ne se relit pas ne compte pas.
# 3. Le fichier vérifié s'appelle amm-vm-AAAAMMJJ-HHMMSS.dump.gpg : même format que les
#    sauvegardes de Render (scripts/verify_backup.sh et restaurer_base.sh le relisent).
# 4. etat.json dit ce qui s'est passé : l'application le lit pour avertir si la sauvegarde
#    échoue ou ne tourne plus, et pour copier le fichier hors de la machine.
# 5. Rétention : au-delà de BACKUP_RETENTION_DAYS jours, sauf les 7 dernières vérifiées.
set -euo pipefail

dir=${BACKUP_DIR:-/backups}
retention=${BACKUP_RETENTION_DAYS:-30}
db=${PGDATABASE:-amm}
scratch=${BACKUP_SCRATCH_DB:-amm_essai_restauration}
keep=7
stamp=$(date -u +%Y%m%d-%H%M%S)
name="amm-vm-${stamp}.dump.gpg"
part="${dir}/${name}.part"

log() { echo "[sauvegarde] $*" >&2; }
# Messages d'erreur : textes fixes de ce script, sans guillemets (etat.json reste valide).
state() {
  printf '{"at":"%s","ok":%s,"file":"%s","bytes":%s,"error":"%s"}\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "$3" "$4" > "${dir}/etat.json.part"
  chmod 644 "${dir}/etat.json.part"
  mv "${dir}/etat.json.part" "${dir}/etat.json"
}
drop_scratch() { dropdb --if-exists --force "$scratch" >/dev/null 2>&1 || true; }
# Toute sortie avant la fin est un échec, prévu (die) ou non : il est écrit dans etat.json, la
# base d'essai est retirée et le fichier non vérifié est mis de côté (.echec, jamais copié).
done_ok=0
reason="erreur inattendue (journal : scripts/serveur/compose.sh logs backup)"
finish() {
  [ "$done_ok" = 1 ] && return
  log "ECHEC : ${reason}"
  drop_scratch
  if [ -e "$part" ]; then mv "$part" "${dir}/${name%.dump.gpg}.echec"; fi
  state false "" 0 "$reason"
}
trap finish EXIT
die() { reason=$1; exit 1; }
sql() { psql -d "$scratch" -Atq -c "$1"; }
decrypt() {
  gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 3 --decrypt "$1" \
    3<<< "$BACKUP_PASSPHRASE"
}

mkdir -p "$dir"
[ "$scratch" != "$db" ] || die "la base d'essai porte le nom de la vraie base"
[ -n "${BACKUP_PASSPHRASE:-}" ] \
  || die "phrase secrète absente (BACKUP_PASSPHRASE) : aucune sauvegarde en clair n'est écrite"

log "${stamp} : base ${db}"
pg_dump --format=custom --no-owner --no-acl "$db" \
  | gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-fd 3 \
      --symmetric --cipher-algo AES256 --output "$part" 3<<< "$BACKUP_PASSPHRASE" \
  || die "pg_dump ou le chiffrement a échoué"
[ -s "$part" ] || die "sauvegarde vide"

log "essai de restauration dans la base ${scratch}"
drop_scratch
createdb "$scratch" || die "création de la base d'essai impossible"
decrypt "$part" | pg_restore --no-owner --no-acl --exit-on-error -d "$scratch" \
  || die "la sauvegarde ne se restaure pas"
tables=$(sql "select count(*) from information_schema.tables where table_schema = 'public'") \
  || die "base d'essai illisible"
migrations=$(sql "select count(*) from django_migrations" 2>/dev/null) || die "base restaurée sans migrations"
[ "$tables" -gt 0 ] && [ "$migrations" -gt 0 ] || die "base restaurée vide"
for table in amm_marketingauthorization catalog_product catalog_country accounts_user; do
  [ "$(sql "select exists (select 1 from ${table})" 2>/dev/null)" = "t" ] \
    || die "table ${table} vide ou absente après restauration"
done
drop_scratch

chmod 644 "$part"
mv "$part" "${dir}/${name}"
bytes=$(stat -c %s "${dir}/${name}")
state true "$name" "$bytes" ""
done_ok=1
log "OK : ${name} (${bytes} octets, ${tables} tables, ${migrations} migrations), relue et restaurée"

# Rétention : jamais les 7 dernières vérifiées, même anciennes (si la sauvegarde est en panne
# depuis longtemps, les dernières bonnes restent).
deleted=0
while IFS= read -r old; do
  if [ -n "$(find "$old" -mtime "+${retention}" -print)" ]; then
    rm -f -- "$old"
    deleted=$((deleted + 1))
  fi
done < <(find "$dir" -maxdepth 1 -type f -name 'amm-vm-*.dump.gpg' | sort -r | tail -n "+$((keep + 1))")
find "$dir" -maxdepth 1 -type f \( -name 'amm-vm-*.echec' -o -name 'amm-vm-*.part' \) -mtime "+${retention}" -delete
log "rétention ${retention} j : ${deleted} sauvegarde(s) ancienne(s) retirée(s)"
