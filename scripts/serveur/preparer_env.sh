#!/usr/bin/env bash
# Crée le fichier .env d'AMM GH sur un serveur, avec des secrets tirés au hasard sur place :
# personne ne les saisit ni ne les voit passer (ils ne quittent pas la machine).
#
#   scripts/serveur/preparer_env.sh amm.102-203-86-8.sslip.io            # adresse publique HTTPS
#   scripts/serveur/preparer_env.sh amm.102-203-86-8.sslip.io --essai    # essai privé d'abord
#
# --essai : l'application n'est ouverte que par un tunnel SSH, en HTTP sur
# http://localhost:8081 ; le cookie de session n'est alors pas réservé à HTTPS. À la mise en
# service publique, passer AUTH_REFRESH_COOKIE_SECURE à 1 et FRONTEND_URL à l'adresse HTTPS.
#
# Un .env existant n'est jamais écrasé. Le stockage des scans (S3) et la synchronisation GHPL
# (Nextcloud) ne sont pas renseignés : à ajouter à la main pour la mise en service.
set -euo pipefail
cd "$(dirname "$0")/../.."

domain=${1:?usage : scripts/serveur/preparer_env.sh <adresse publique sans https://> [--essai]}
essai=0
[ "${2:-}" = "--essai" ] && essai=1
[ ! -e .env ] || { echo "[amm-gh] ERREUR : .env existe déjà, il n'est pas écrasé" >&2; exit 1; }

secret() { openssl rand -base64 64 | tr -d '\n=+/' | cut -c1-"$1"; }
pg_password=$(secret 32)
local_url="http://localhost:8081"
if [ "$essai" = 1 ]; then
  frontend_url=$local_url
  origins="https://${domain},${local_url},http://127.0.0.1:8081"
  cookie_secure=0
else
  frontend_url="https://${domain}"
  origins="https://${domain}"
  cookie_secure=1
fi

umask 077
cat > .env <<ENV
# AMM GH — créé par scripts/serveur/preparer_env.sh le $(date +%F). Ne pas versionner.
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=$(secret 64)
ALLOWED_HOSTS=${domain},localhost,127.0.0.1,backend
CORS_ALLOWED_ORIGINS=${origins}
CSRF_TRUSTED_ORIGINS=${origins}
FRONTEND_URL=${frontend_url}
AUTH_REFRESH_COOKIE_SECURE=${cookie_secure}
TIME_ZONE=Africa/Dakar
# Deux relais devant Django sur un serveur partagé : le portier (Caddy) puis nginx.
NUM_PROXIES=2

POSTGRES_USER=amm
POSTGRES_DB=amm
POSTGRES_PASSWORD=${pg_password}
DATABASE_URL=postgres://amm:${pg_password}@postgres:5432/amm
REDIS_URL=redis://redis:6379/0

# Version des images (ghcr.io/alamine2003/amm-innov-*) : latest, ou le début d'un commit.
TAG=latest
WEB_CONCURRENCY=2
CELERY_CONCURRENCY=2

# Scans : sur le disque du serveur tant que le stockage S3 n'est pas renseigné.
DOCUMENT_STORAGE=local

# Serveur partagé (docker-compose.partage.yml) : nginx d'AMM GH visible de la machine seulement.
AMM_BIND=127.0.0.1:8081
DOMAIN=${domain}
# Exigé par docker-compose.prod.yml même sans Grafana (profil « supervision »).
GRAFANA_ADMIN_PASSWORD=$(secret 32)
ENV
echo "[amm-gh] .env créé (lisible par son propriétaire seulement)$([ "$essai" = 1 ] && echo ' — mode essai : http://localhost:8081 par tunnel SSH')"
