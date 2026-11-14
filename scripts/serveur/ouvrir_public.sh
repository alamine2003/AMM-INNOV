#!/usr/bin/env bash
# Ouvre AMM GH au public sur un serveur partagé, à travers le Caddy déjà en place (le
# « portier », celui de JUSTI GH sur le Serveur 01 Stellarix), ou la referme.
#
#   sudo scripts/serveur/ouvrir_public.sh              # ouvre https://<DOMAIN du .env>
#   sudo scripts/serveur/ouvrir_public.sh --fermer     # revient à l'essai privé
#
# Ce que fait l'ouverture, dans cet ordre, en s'arrêtant à la première anomalie :
#  1. le nginx d'AMM GH écoute sur la passerelle Docker (172.17.0.1:8081) au lieu de la boucle
#     locale : joignable de la machine et de ses conteneurs, jamais de l'extérieur ;
#  2. le portier doit le joindre : contrôlé AVANT de toucher à sa configuration ;
#  3. chez le portier : un fichier `caddy/voisins/amm-gh.caddy` (le site d'AMM GH) et, une
#     seule fois, la ligne `import caddy/voisins/*.caddy` à la fin de son Caddyfile (copie de
#     sauvegarde `Caddyfile.avant-amm-gh`) ;
#  4. la configuration est validée par Caddy lui-même ; refusée, le fichier est retiré et rien
#     n'est rechargé ; acceptée, Caddy la recharge sans couper les visites en cours ;
#  5. AMM GH passe en HTTPS (adresse publique, cookie de session réservé à HTTPS).
#
# Réglages : PORTIER_DIR (/home/deploy/justi-innov), PORTIER_CONTENEUR (justi-innov-caddy-1),
# AMM_PORT (8081). Les fichiers du voisin sont écrits en root : c'est un acte d'exploitation.
set -euo pipefail
cd "$(dirname "$0")/../.."

mode=ouvrir
[ "${1:-}" = "--fermer" ] && mode=fermer
dir=${PORTIER_DIR:-/home/deploy/justi-innov}
caddy=${PORTIER_CONTENEUR:-justi-innov-caddy-1}
port=${AMM_PORT:-8081}
site_file="$dir/caddy/voisins/amm-gh.caddy"
import_line='import caddy/voisins/*.caddy'

log() { echo "[amm-gh] $*" >&2; }
die() { log "ERREUR : $*"; exit 1; }
compose() { scripts/serveur/compose.sh "$@"; }
get_env() { sed -n "s/^$1=//p" .env | tail -1; }
set_env() { # set_env CLE VALEUR : remplace la ligne, ou l'ajoute
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
reload() { docker exec "$caddy" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; }

[ -f .env ] || die "pas de fichier .env ici (scripts/serveur/preparer_env.sh)"
[ -f "$dir/Caddyfile" ] && [ -d "$dir/caddy" ] || die "portier introuvable dans $dir (PORTIER_DIR)"
docker inspect "$caddy" >/dev/null 2>&1 || die "conteneur du portier introuvable : $caddy (PORTIER_CONTENEUR)"
domain=$(get_env DOMAIN)
[ -n "$domain" ] || die "DOMAIN absent du .env"
case "$domain" in http://*) url=$domain ;; *) url="https://$domain" ;; esac

if [ "$mode" = fermer ]; then
  rm -f "$site_file"
  reload || die "le portier n'a pas rechargé sa configuration (docker logs $caddy)"
  set_env AMM_BIND "127.0.0.1:${port}"
  set_env FRONTEND_URL "http://localhost:${port}"
  set_env CORS_ALLOWED_ORIGINS "${url},http://localhost:${port},http://127.0.0.1:${port}"
  set_env CSRF_TRUSTED_ORIGINS "${url},http://localhost:${port},http://127.0.0.1:${port}"
  set_env AUTH_REFRESH_COOKIE_SECURE 0
  compose up -d >/dev/null 2>&1 || die "redémarrage d'AMM GH impossible (scripts/serveur/compose.sh up -d)"
  log "OK : AMM GH n'est plus ouverte au public ; essai privé sur http://localhost:${port} par tunnel SSH"
  exit 0
fi

gateway=$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}')
[ -n "$gateway" ] || die "passerelle Docker introuvable"
previous_bind=$(get_env AMM_BIND)

log "1/5 nginx d'AMM GH sur ${gateway}:${port}"
set_env AMM_BIND "${gateway}:${port}"
compose up -d frontend >/dev/null 2>&1 || die "redémarrage de l'interface impossible"

log "2/5 le portier joint-il AMM GH ?"
reached=""
for _ in $(seq 1 20); do
  reached=$(docker exec "$caddy" wget -T 5 -qO- "http://${gateway}:${port}/healthz" 2>/dev/null || true)
  [ "$reached" = "ok" ] && break
  sleep 2
done
if [ "$reached" != "ok" ]; then
  set_env AMM_BIND "${previous_bind:-127.0.0.1:${port}}"
  compose up -d frontend >/dev/null 2>&1 || true
  die "le portier ($caddy) ne joint pas http://${gateway}:${port} : rien n'a été modifié chez lui (pare-feu de la machine ?)"
fi

log "3/5 site d'AMM GH chez le portier"
mkdir -p "$dir/caddy/voisins"
cat > "$site_file" <<CADDY
# AMM GH, application voisine sur cette machine (/home/deploy/amm-gh). Écrit par
# scripts/serveur/ouvrir_public.sh du dépôt AMM-INNOV ; retiré par --fermer.
${domain} {
	encode zstd gzip

	header Strict-Transport-Security "max-age=31536000"

	# Dossiers pays : 250 Mo côté application, plus l'enveloppe multipart.
	request_body {
		max_size 260MB
	}

	# nginx d'AMM GH, sur la passerelle Docker de la machine. Les deux applications ne
	# partagent aucun réseau Docker : leurs services portent les mêmes noms.
	reverse_proxy ${gateway}:${port} {
		transport http {
			dial_timeout 3s
			response_header_timeout 300s
			read_timeout 900s
		}
	}

	log {
		output stdout
		format console
	}
}
CADDY
if ! grep -qF "$import_line" "$dir/Caddyfile"; then
  [ -e "$dir/Caddyfile.avant-amm-gh" ] || cp -p "$dir/Caddyfile" "$dir/Caddyfile.avant-amm-gh"
  # Ajout en place : le Caddyfile est monté fichier par fichier dans le conteneur.
  printf '\n# Applications voisines hébergées sur cette machine (AMM GH).\n%s\n' "$import_line" >> "$dir/Caddyfile"
fi

log "4/5 validation puis rechargement du portier"
if ! docker exec "$caddy" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  rm -f "$site_file"
  die "Caddy refuse la configuration : le site d'AMM GH a été retiré, le portier n'a pas été rechargé et continue comme avant"
fi
if ! reload; then
  rm -f "$site_file"
  die "rechargement refusé : le site d'AMM GH a été retiré, le portier continue comme avant (docker logs $caddy)"
fi

log "5/5 AMM GH en adresse publique"
set_env FRONTEND_URL "$url"
set_env CORS_ALLOWED_ORIGINS "$url"
set_env CSRF_TRUSTED_ORIGINS "$url"
case "$url" in https://*) set_env AUTH_REFRESH_COOKIE_SECURE 1 ;; esac
compose up -d >/dev/null 2>&1 || die "redémarrage d'AMM GH impossible (scripts/serveur/compose.sh up -d)"

host=${domain#http://}
answer=""
for _ in $(seq 1 30); do
  case "$url" in
    https://*) answer=$(curl -sS -m 10 --resolve "${host}:443:127.0.0.1" "${url}/api/v1/health" 2>/dev/null || true) ;;
    *) answer=$(curl -sS -m 10 -H "Host: ${host}" "http://127.0.0.1/api/v1/health" 2>/dev/null || true) ;;
  esac
  case "$answer" in *'"status"'*) break ;; esac
  sleep 4
done
case "$answer" in
  *'"status"'*) log "OK : ${url} répond — ${answer}" ;;
  *) log "ouvert, mais ${url} ne répond pas encore (certificat en cours ?). Réessayer dans une minute : docker logs --tail 30 $caddy" ;;
esac
