#!/usr/bin/env bash
# Docker Compose d'AMM GH sur un serveur partagé, sans retaper les deux fichiers :
#   scripts/serveur/compose.sh up -d      scripts/serveur/compose.sh ps
#   scripts/serveur/compose.sh logs -f backend
# À lancer depuis le dossier d'installation (celui qui contient .env).
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { echo "[amm-gh] ERREUR : pas de fichier .env ici (scripts/serveur/preparer_env.sh)" >&2; exit 1; }
exec docker compose -f docker-compose.prod.yml -f docker-compose.partage.yml "$@"
