#!/usr/bin/env bash
# Autorise une interface servie ailleurs (Cloudflare Pages) à utiliser l'API de ce serveur, ou
# retire cette autorisation.
#
#   sudo scripts/serveur/brancher_interface.sh https://amm-gh.pages.dev
#   sudo scripts/serveur/brancher_interface.sh https://amm-gh.pages.dev --retirer
#
# Brancher : l'adresse est ajoutée aux origines acceptées par l'API (appels, formulaires, temps
# réel), les liens des notifications mènent à cette interface, et le cookie de session accepte
# de voyager entre les deux adresses (SameSite=None, réservé à HTTPS). L'interface servie par
# ce serveur continue de marcher. Retirer : l'inverse, l'interface du serveur redevient la seule.
set -euo pipefail
cd "$(dirname "$0")/../.."

origin=${1:?usage : scripts/serveur/brancher_interface.sh <https://adresse-de-l-interface> [--retirer]}
mode=brancher
[ "${2:-}" = "--retirer" ] && mode=retirer
origin=${origin%/}

log() { echo "[amm-gh] $*" >&2; }
die() { log "ERREUR : $*"; exit 1; }
compose() { scripts/serveur/compose.sh "$@"; }
get_env() { sed -n "s/^$1=//p" .env | tail -1 | sed "s/^'\(.*\)'$/\1/"; }
set_env() {
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
without() { # without LISTE ORIGINE : la liste sans cette origine
  echo "$1" | tr ',' '\n' | grep -vxF "$2" | paste -sd, -
}

[ -f .env ] || die "pas de fichier .env ici (scripts/serveur/preparer_env.sh)"
[[ "$origin" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]] || die "adresse attendue : https://nom-de-domaine, sans chemin"
domain=$(get_env DOMAIN)
[ -n "$domain" ] || die "DOMAIN absent du .env"
api="https://${domain}"
[ "$(get_env AUTH_REFRESH_COOKIE_SECURE)" = 1 ] \
  || die "l'API n'est pas encore ouverte en HTTPS (scripts/serveur/ouvrir_public.sh) : le cookie de session ne voyagerait pas"

cp -p .env .env.avant
for key in CORS_ALLOWED_ORIGINS CSRF_TRUSTED_ORIGINS; do
  kept=$(without "$(get_env "$key")" "$origin")
  if [ "$mode" = brancher ]; then set_env "$key" "${kept:+${kept},}${origin}"; else set_env "$key" "${kept:-$api}"; fi
done
if [ "$mode" = brancher ]; then
  set_env FRONTEND_URL "$origin"
  set_env AUTH_REFRESH_COOKIE_SAMESITE None
else
  set_env FRONTEND_URL "$api"
  set_env AUTH_REFRESH_COOKIE_SAMESITE Lax
fi
compose up -d >/dev/null 2>&1 || die "redémarrage d'AMM GH impossible (scripts/serveur/compose.sh up -d) ; configuration d'avant : .env.avant"

# La preuve : l'API répond-elle à cette origine comme un navigateur le demande ?
headers=""
for _ in $(seq 1 30); do
  headers=$(curl -sS -m 10 -o /dev/null -D - --resolve "${domain}:443:127.0.0.1" \
    -H "Origin: ${origin}" "${api}/api/v1/health" 2>/dev/null | tr -d '\r' || true)
  case "$headers" in HTTP*" 200"*) break ;; esac
  sleep 4
done
case "$headers" in
  HTTP*" 200"*) ;;
  *) die "l'API ne répond pas après le redémarrage (scripts/serveur/compose.sh logs --tail 30 backend) ; configuration d'avant : .env.avant" ;;
esac
allowed=$(echo "$headers" | sed -n 's/^access-control-allow-origin: //Ip')
if [ "$mode" = brancher ]; then
  [ "$allowed" = "$origin" ] || die "l'API répond mais n'accepte pas ${origin} ; configuration d'avant : .env.avant"
  log "OK : ${api} accepte l'interface ${origin}"
else
  [ -z "$allowed" ] || die "l'API accepte encore ${origin}"
  log "OK : ${api} n'accepte plus l'interface ${origin}"
fi
