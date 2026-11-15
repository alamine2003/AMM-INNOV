#!/usr/bin/env bash
# Règle la configuration d'AMM GH sur son serveur, sans éditer le fichier .env à la main.
#
#   sudo scripts/serveur/configurer.sh BACKUP_PASSPHRASE        # secret : saisie masquée
#   sudo scripts/serveur/configurer.sh S3_SECRET_KEY            # secret : saisie masquée
#   sudo scripts/serveur/configurer.sh DOCUMENT_STORAGE=s3 S3_REGION=auto   # valeurs ordinaires
#
# Un secret (clé dont le nom contient KEY, SECRET, PASSWORD, PASSPHRASE ou TOKEN) n'est jamais
# accepté sur la ligne de commande : il est demandé au clavier, deux fois, sans être affiché,
# et ne reste donc pas dans l'historique du terminal.
# BACKUP_PASSPHRASE va dans .env.sauvegarde, lu par le seul service de sauvegarde ; le reste
# va dans .env. Une clé déjà présente est remplacée (le fichier d'avant est gardé en .avant).
# Les services ne relisent ces fichiers qu'à leur recréation : scripts/serveur/compose.sh up -d
set -euo pipefail
cd "$(dirname "$0")/../.."

log() { echo "[amm-gh] $*" >&2; }
die() { log "ERREUR : $*"; exit 1; }
[ $# -gt 0 ] || die "usage : scripts/serveur/configurer.sh <CLE secrète> | <CLE=valeur> [<CLE=valeur> …]"
[ -f .env ] || die "pas de fichier .env ici (scripts/serveur/preparer_env.sh)"

is_secret() { [[ "$1" =~ (KEY|SECRET|PASSWORD|PASSPHRASE|TOKEN) ]]; }
write() { # write CLE VALEUR
  local key=$1 value=$2 file=.env tmp
  [ "$key" = BACKUP_PASSPHRASE ] && file=.env.sauvegarde
  [ -n "$value" ] || die "valeur vide pour ${key} : rien n'est écrit"
  case "$value" in
    *$'\n'* | *"'"*) die "${key} : la valeur ne doit contenir ni apostrophe ni retour à la ligne" ;;
  esac
  umask 077
  tmp=$(mktemp "${file}.XXXXXX")
  if [ -f "$file" ]; then
    cp -p "$file" "${file}.avant"
    grep -v "^${key}=" "$file" > "$tmp" || true
  fi
  # Entre apostrophes : Docker Compose prend la valeur telle quelle (ni « $ » ni espace interprété).
  printf "%s='%s'\n" "$key" "$value" >> "$tmp"
  mv "$tmp" "$file"
  chmod 600 "$file"
  log "${key} enregistré dans ${file}"
}

for arg in "$@"; do
  key=${arg%%=*}
  [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || die "nom de clé invalide : ${key}"
  if [ "$arg" != "$key" ]; then
    is_secret "$key" && die "${key} est un secret : lancer « configurer.sh ${key} » sans valeur, elle sera demandée au clavier"
    write "$key" "${arg#*=}"
  else
    IFS= read -rsp "${key} (saisie masquée) : " value; echo >&2
    IFS= read -rsp "${key}, une seconde fois : " again; echo >&2
    [ "$value" = "$again" ] || die "les deux saisies diffèrent, rien n'est écrit"
    write "$key" "$value"
  fi
done
log "à prendre en compte par : scripts/serveur/compose.sh up -d"
