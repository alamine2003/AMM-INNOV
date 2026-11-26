#!/usr/bin/env bash
# Agent de livraison d'AMM GH sur son serveur (1.3.9).
#
# Lancé chaque minute par systemd (scripts/serveur/installer_livraison.sh), il demande à GitHub
# si une version a été approuvée pour ce serveur, et l'installe. Le serveur n'est joignable que
# par le VPN : c'est lui qui va chercher le travail, GitHub n'entre jamais.
#
#   1. GitHub : l'étiquette vX.Y.Z est posée, le workflow « Livraison » vérifie la version et
#      prépare ses images, puis attend l'approbation de Mohamed (environnement production).
#   2. Une fois approuvée, le workflow inscrit un déploiement « serveur-stellarix » en attente
#      (état queued) et attend la réponse du serveur.
#   3. Cet agent le voit et vérifie qu'il vient bien du workflow (github-actions[bot]), que
#      l'étiquette est sur main et pointe sur le commit annoncé.
#   4. Si une commande d'administration tourne (relire_congo …), l'installation est reportée :
#      un redémarrage l'interromprait. Elle repart seule à la minute où la commande se termine.
#   5. Sauvegarde chiffrée et vérifiée de la base (scripts/serveur/sauvegarder.sh). Si elle
#      échoue, rien n'est installé.
#   6. Installation : les images de la version sont téléchargées d'abord (si GHCR refuse, rien
#      n'a changé) ; puis git checkout de l'étiquette, TAG=X.Y.Z dans .env (images de la
#      version, pas « latest »), up -d.
#   7. Contrôle : l'API doit répondre « ok », base et Redis en marche, avec le numéro attendu.
#   8. Sinon, retour à la version d'avant, avec ses images déjà sur le serveur (rien n'est
#      retéléchargé ; la base n'est pas restaurée : la sauvegarde de l'étape 5 est là pour ça,
#      scripts/serveur/restaurer_base.sh).
#   9. Le résultat est renvoyé à GitHub : le workflow passe au vert ou au rouge.
#
# À la main (même effet qu'un passage du minuteur) :  sudo scripts/serveur/livrer.sh
# Journal : livraisons/journal.log, et  journalctl -u amm-gh-livraison
#
# Le jeton GitHub (GITHUB_DEPLOY_TOKEN, droit « Deployments » sur ce seul dépôt) est dans
# .env.livraison, lu par ce script seulement : l'application ne le voit pas.
#   sudo scripts/serveur/configurer.sh GITHUB_DEPLOY_TOKEN
set -euo pipefail

dir=${AMM_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}
repo=${LIVRAISON_DEPOT:-alamine2003/AMM-INNOV}
api_base=${LIVRAISON_API:-https://api.github.com}
environment=${LIVRAISON_ENVIRONNEMENT:-serveur-stellarix}
compose=${LIVRAISON_COMPOSE:-$dir/scripts/serveur/compose.sh}
tries=${LIVRAISON_ESSAIS:-36}
pause=${LIVRAISON_PAUSE:-5}
public_url=${LIVRAISON_URL:-https://amm.102-203-86-8.sslip.io}
docker=${LIVRAISON_DOCKER:-docker}
# Le workflow GitHub crée le déploiement avec GITHUB_TOKEN : son auteur est ce compte-là.
bot=${LIVRAISON_AUTEUR:-github-actions[bot]}

cd "$dir"
mkdir -p livraisons
chmod 700 livraisons

# Réglages Docker propres à l'agent, vides : les images d'AMM GH sont publiques et se
# téléchargent sans connexion. Sous systemd, Docker lirait sinon /root/.docker/config.json, dont
# la connexion à ghcr.io (posée pour une autre application) est refusée par GHCR, qui rejette un
# jeton invalide même pour une image publique (livraison de la 1.3.9, 26/11/2026).
export DOCKER_CONFIG=${LIVRAISON_DOCKER_CONFIG:-$dir/livraisons/docker}
mkdir -p "$DOCKER_CONFIG"
journal=livraisons/journal.log

log() { echo "[livraison] $(date '+%F %T') $*" | tee -a "$journal" >&2; }

# Un seul passage à la fois (le minuteur ne relance qu'après la fin, mais un lancement à la main
# peut tomber en même temps).
exec 9> livraisons/.verrou
flock -n 9 || exit 0

token=$( (sed -n "s/^GITHUB_DEPLOY_TOKEN=//p" .env.livraison 2>/dev/null || true) | tail -n 1)
token=${token#\'}
token=${token%\'}
if [ -z "$token" ]; then
  echo "[livraison] jeton absent : sudo scripts/serveur/configurer.sh GITHUB_DEPLOY_TOKEN" >&2
  exit 0
fi

# api MÉTHODE CHEMIN [JSON] : le jeton passe par un fichier de configuration de curl, jamais
# sur la ligne de commande (visible de tous dans la liste des processus).
api() {
  local method=$1 path=$2 data=${3:-}
  local args=(-fsS --max-time 30 -X "$method"
    -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28")
  if [ -n "$data" ]; then
    args+=(-H "Content-Type: application/json" --data-binary @-)
  fi
  curl -K <(printf 'header = "Authorization: Bearer %s"\n' "$token") "${args[@]}" \
    "${api_base}${path}" <<< "$data"
}

json() { # json CLÉ=VALEUR … → objet JSON (les valeurs sont des chaînes)
  python3 -c 'import json, sys
print(json.dumps(dict(arg.split("=", 1) for arg in sys.argv[1:])))' "$@"
}

# status ÉTAT DESCRIPTION : réponse au workflow (140 caractères au plus chez GitHub).
status() {
  local description=${2:0:140}
  api POST "/repos/${repo}/deployments/${deployment}/statuses" \
    "$(json state="$1" description="$description" environment_url="$public_url")" >/dev/null \
    || log "réponse à GitHub impossible (${1} : ${description})"
}

# --- 1. Une version approuvée attend-elle ce serveur ? -----------------------------------------
listing=$(api GET "/repos/${repo}/deployments?environment=${environment}&per_page=1") || {
  echo "[livraison] GitHub injoignable" >&2
  exit 0
}
read -r deployment ref sha creator < <(python3 -c 'import json, sys
items = json.load(sys.stdin)
if items:
    d = items[0]
    print(d["id"], d["ref"], (d.get("payload") or {}).get("sha", "-") or "-",
          (d.get("creator") or {}).get("login", "-"))' <<< "$listing") || exit 0
[ -n "${deployment:-}" ] || exit 0

statuses=$(api GET "/repos/${repo}/deployments/${deployment}/statuses?per_page=1") || exit 0
read -r state description < <(python3 -c 'import json, sys
items = json.load(sys.stdin)
print(items[0]["state"], items[0].get("description") or "") if items else print("aucun")' \
  <<< "$statuses") || exit 0
[ "$state" = queued ] || exit 0

# --- 2. Contrôles : provenance, étiquette, commit -------------------------------------------------
refuse() {
  log "REFUSÉ ${ref} : $1"
  status error "Refusé par le serveur : $1"
  exit 1
}
[ "$creator" = "$bot" ] || refuse "déploiement créé par ${creator}, pas par le workflow"
[[ "$ref" =~ ^v([0-9]+\.[0-9]+\.[0-9]+)$ ]] || refuse "« ${ref} » n'est pas une étiquette vX.Y.Z"
version=${BASH_REMATCH[1]}

git fetch --quiet --tags --force origin || refuse "git fetch impossible"
target=$(git rev-parse --verify --quiet "refs/tags/${ref}^{commit}") \
  || refuse "étiquette ${ref} introuvable"
[ "$target" = "$sha" ] || refuse "${ref} pointe sur ${target:0:7}, le workflow annonçait ${sha:0:7}"
git merge-base --is-ancestor "$target" origin/main || refuse "${ref} n'est pas sur main"
# Un fichier du dépôt modifié à la main sur le serveur serait écrasé ou bloquerait le checkout.
changed=$(git status --porcelain --untracked-files=no | head -n 3 | tr '\n' ' ')
[ -z "$changed" ] || refuse "fichiers modifiés à la main sur le serveur : ${changed% }"

# --- 3. Rien d'important en cours ? ----------------------------------------------------------
busy=$("$compose" top worker backend 2>/dev/null | grep -o "manage\.py [a-z_]*" | sort -u | tr '\n' ' ' || true)
if [ -n "$busy" ]; then
  wait_note="En attente : une commande tourne sur le serveur (${busy% }), reprise dès sa fin"
  if [ "$description" != "$wait_note" ]; then
    log "${ref} reportée : ${busy% } en cours"
    status queued "$wait_note"
  fi
  exit 0
fi

previous_ref=$(git describe --tags --exact-match HEAD 2>/dev/null || git rev-parse HEAD)
previous_tag=$(sed -n "s/^TAG=//p" .env | tail -n 1 | tr -d "'\"")
previous_tag=${previous_tag:-latest}
previous_version=$(cat backend/VERSION)
log "${ref} approuvée : installation (en place : ${previous_version}, images ${previous_tag})"
status in_progress "Sauvegarde de la base avant installation"

# --- 4. Sauvegarde ------------------------------------------------------------------------------
if ! "$compose" exec -T backup /scripts/serveur/sauvegarder.sh >> "$journal" 2>&1; then
  log "ÉCHEC ${ref} : la sauvegarde d'avant installation a échoué, rien n'a été changé"
  status failure "Sauvegarde de la base en échec : rien n'a été installé (journal : livraisons/journal.log)"
  exit 1
fi

# --- 5. Installation ----------------------------------------------------------------------------
set_tag() { # TAG=… dans .env, le reste du fichier inchangé
  local tmp
  tmp=$(mktemp .env.XXXXXX)
  grep -v '^TAG=' .env > "$tmp" || true
  printf "TAG='%s'\n" "$1" >> "$tmp"
  chmod --reference=.env "$tmp"
  mv "$tmp" .env
}

healthy() { # healthy VERSION : l'API répond ok, base et Redis en marche, avec ce numéro
  local answer
  for _ in $(seq 1 "$tries"); do
    answer=$("$compose" exec -T frontend wget -qO- http://127.0.0.1/api/v1/health 2>/dev/null || true)
    if python3 -c 'import json, sys
h = json.loads(sys.argv[1])
ok = h.get("status") == "ok" and h.get("database") and h.get("redis")
sys.exit(0 if ok and h.get("version") == sys.argv[2] else 1)' "$answer" "$1" 2>/dev/null; then
      return 0
    fi
    sleep "$pause"
  done
  health_seen=${answer:-pas de réponse}
  return 1
}

switch() { # switch ÉTIQUETTE TAG : code et images de cette version, démarrés
  git checkout --quiet "$1" && set_tag "$2" && "$compose" up -d >> "$journal" 2>&1
}

# Images d'abord : si elles ne viennent pas, rien n'a encore changé sur le serveur.
status in_progress "Téléchargement des images ${version}"
if ! TAG="$version" "$compose" pull --quiet backend worker beat frontend >> "$journal" 2>&1; then
  log "ÉCHEC ${ref} : images ${version} inaccessibles, rien n'a été changé"
  status failure "Images ${version} inaccessibles sur GHCR : rien n'a été changé (journal : livraisons/journal.log)"
  exit 1
fi

status in_progress "Installation de ${version}"
reason=""
if ! switch "$ref" "$version"; then
  reason="installation interrompue (git ou démarrage)"
elif ! healthy "$version"; then
  reason="l'API ne répond pas ${version} en bonne santé (${health_seen:0:60})"
fi

if [ -z "$reason" ]; then
  log "OK ${ref} en service"
  status success "AMM GH ${version} en service (base sauvegardée juste avant)"
  "$docker" image prune -f >/dev/null 2>&1 || true
  exit 0
fi

# --- 6. Retour à la version d'avant ------------------------------------------------------------
log "ÉCHEC ${ref} : ${reason} ; retour à ${previous_version}"
if switch "$previous_ref" "$previous_tag" && healthy "$previous_version"; then
  back="retour à ${previous_version} réussi"
else
  back="RETOUR À ${previous_version} ÉCHOUÉ : intervenir sur le serveur"
fi
log "${back}"
status failure "${version} : ${reason} ; ${back}"
exit 1
