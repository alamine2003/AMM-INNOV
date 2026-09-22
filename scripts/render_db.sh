#!/usr/bin/env bash
# Base Postgres gratuite de Render : sauvegarde, création et renouvellement.
#
# Render supprime une base gratuite 30 jours après sa création, et n'en autorise qu'une par
# espace de travail. Ce script la renouvelle avant l'échéance, sans rien perdre :
#   sauvegarde -> suppression de l'ancienne -> création -> restauration -> DATABASE_URL -> déploiement.
# La sauvegarde est écrite AVANT toute suppression ; si une étape échoue, elle reste dans
# $BACKUP_DIR (et dans les artefacts GitHub quand le script tourne dans la CI).
#
# Usage :
#   scripts/render_db.sh status               # âge de la base, jours restants
#   scripts/render_db.sh backup               # pg_dump dans $BACKUP_DIR
#   scripts/render_db.sh ensure               # crée la base si aucune n'existe, et branche l'API
#   scripts/render_db.sh rotate [--force]     # renouvelle si âge >= ROTATE_AFTER_DAYS (25)
#   scripts/render_db.sh import <DATABASE_URL> # copie une base externe (Railway) dans Render
#   scripts/render_db.sh restore <fichier.dump> # restaure une sauvegarde dans la base Render
#
# Variables : RENDER_API_KEY (obligatoire), RENDER_SERVICE (amm-innov-api), RENDER_DB_NAME
# (amm-innov-db), RENDER_REGION (frankfurt), ROTATE_AFTER_DAYS (25), BACKUP_DIR (./backups).
# Outils : curl, jq, date GNU (Linux, CI) et pg_dump/pg_restore de version PG_VERSION (18)
# (ou docker, à défaut).
set -euo pipefail

API="${RENDER_API_URL:-https://api.render.com/v1}"
: "${RENDER_API_KEY:?RENDER_API_KEY manquant (Render, Account settings, API keys)}"
SERVICE_NAME="${RENDER_SERVICE:-amm-innov-api}"
DB_NAME="${RENDER_DB_NAME:-amm-innov-db}"
REGION="${RENDER_REGION:-frankfurt}"
ROTATE_AFTER_DAYS="${ROTATE_AFTER_DAYS:-25}"
PG_VERSION="${PG_VERSION:-18}"   # même version majeure que la base Railway d'origine
BACKUP_DIR="${BACKUP_DIR:-./backups}"

log() { echo "[render-db] $*" >&2; }
die() { log "ERREUR : $*"; exit 1; }

api() { # api METHODE CHEMIN [JSON]
  local method=$1 path=$2 body=${3:-}
  local args=(-sS --fail-with-body -X "$method" -H "Authorization: Bearer ${RENDER_API_KEY}"
    -H "Accept: application/json")
  [ -n "$body" ] && args+=(-H "Content-Type: application/json" -d "$body")
  curl "${args[@]}" "${API}${path}"
}

pg() { # pg OUTIL ARGS... : binaire local 16+ sinon image docker postgres:16
  local tool=$1; shift
  if command -v "$tool" >/dev/null && "$tool" --version | grep -qE " (${PG_VERSION}|[2-9][0-9])\."; then
    "$tool" "$@"
  else
    docker run --rm -i --network host "postgres:${PG_VERSION}" "$tool" "$@"
  fi
}

service_id() {
  api GET "/services?name=${SERVICE_NAME}&limit=20" \
    | jq -r --arg n "$SERVICE_NAME" '[.[].service | select(.name == $n)][0].id // empty'
}

db_json() { # objet JSON de la base, vide si absente
  api GET "/postgres?name=${DB_NAME}&limit=20" \
    | jq -c --arg n "$DB_NAME" '[.[].postgres | select(.name == $n)][0] // empty'
}

external_url() { api GET "/postgres/$1/connection-info" | jq -r .externalConnectionString; }
internal_url() { api GET "/postgres/$1/connection-info" | jq -r .internalConnectionString; }

age_days() { # jours depuis createdAt
  local created; created=$(jq -r .createdAt <<<"$1")
  echo $(( ( $(date -u +%s) - $(date -u -d "$created" +%s) ) / 86400 ))
}

wait_available() {
  local id=$1 i status
  for i in $(seq 1 60); do
    status=$(api GET "/postgres/${id}" | jq -r .status)
    [ "$status" = "available" ] && return 0
    log "base ${id} : ${status}, attente (${i}/60)…"; sleep 10
  done
  die "la base ${id} n'est pas disponible après 10 minutes"
}

create_db() {
  local owner
  owner=$(api GET "/owners?limit=1" | jq -r '.[0].owner.id')
  log "création de ${DB_NAME} (gratuit, Postgres ${PG_VERSION}, ${REGION})"
  api POST "/postgres" "$(jq -nc --arg n "$DB_NAME" --arg o "$owner" --arg r "$REGION" --arg v "$PG_VERSION" \
    '{name:$n, ownerId:$o, plan:"free", version:$v, region:$r, databaseName:"amm", databaseUser:"amm"}')" \
    | jq -r .id
}

point_service_to() { # branche l'API sur la base et redéploie
  local db_id=$1 sid url
  sid=$(service_id); [ -n "$sid" ] || die "service ${SERVICE_NAME} introuvable"
  url=$(internal_url "$db_id")
  api PUT "/services/${sid}/env-vars/DATABASE_URL" "$(jq -nc --arg v "$url" '{value:$v}')" >/dev/null
  api POST "/services/${sid}/deploys" '{"clearCache":"do_not_clear"}' >/dev/null
  log "DATABASE_URL mis à jour, déploiement de ${SERVICE_NAME} lancé"
}

backup() { # écrit le fichier et affiche son chemin
  local db; db=$(db_json); [ -n "$db" ] || die "aucune base ${DB_NAME}"
  mkdir -p "$BACKUP_DIR"
  local file; file="amm-render-$(date -u +%Y%m%d-%H%M%S).dump"
  log "pg_dump -> ${BACKUP_DIR}/${file}"
  pg pg_dump --format=custom --no-owner --no-acl "$(external_url "$(jq -r .id <<<"$db")")" \
    > "${BACKUP_DIR}/${file}"
  # une sauvegarde illisible ne doit jamais précéder une suppression
  [ -s "${BACKUP_DIR}/${file}" ] && pg pg_restore --list < "${BACKUP_DIR}/${file}" >/dev/null \
    || die "sauvegarde vide ou illisible : ${file}"
  log "sauvegarde OK ($(du -h "${BACKUP_DIR}/${file}" | cut -f1))"
  echo "${BACKUP_DIR}/${file}"
}

restore_into() { # restore_into FICHIER DB_ID
  local file=$1 id=$2
  log "pg_restore ${file} -> ${DB_NAME}"
  pg pg_restore --no-owner --no-acl --clean --if-exists --single-transaction \
    -d "$(external_url "$id")" < "$file"
}

cmd=${1:-status}; shift || true
case "$cmd" in
  status)
    db=$(db_json); [ -n "$db" ] || { log "aucune base ${DB_NAME}"; exit 0; }
    age=$(age_days "$db")
    log "$(jq -r '"\(.name) \(.id) \(.plan) \(.status) créée le \(.createdAt)"' <<<"$db")"
    log "âge ${age} j ; renouvellement à ${ROTATE_AFTER_DAYS} j, suppression par Render à 30 j"
    ;;
  backup) backup >/dev/null ;;
  ensure)
    db=$(db_json)
    if [ -z "$db" ]; then id=$(create_db); wait_available "$id"; point_service_to "$id"
    else log "base présente : $(jq -r .id <<<"$db")"; fi
    ;;
  rotate)
    db=$(db_json); [ -n "$db" ] || die "aucune base ${DB_NAME} : lancer 'ensure'"
    age=$(age_days "$db")
    if [ "${1:-}" != "--force" ] && [ "$age" -lt "$ROTATE_AFTER_DAYS" ]; then
      log "âge ${age} j < ${ROTATE_AFTER_DAYS} j : rien à faire"; exit 0
    fi
    file=$(backup)
    old=$(jq -r .id <<<"$db")
    log "suppression de l'ancienne base ${old} (sauvegarde : ${file})"
    api DELETE "/postgres/${old}" >/dev/null
    for _ in $(seq 1 30); do [ -z "$(db_json)" ] && break; sleep 5; done
    id=$(create_db); wait_available "$id"
    restore_into "$file" "$id"
    point_service_to "$id"
    log "renouvellement terminé : ${old} -> ${id}"
    ;;
  import)
    src=${1:?usage : import <DATABASE_URL source>}
    db=$(db_json); [ -n "$db" ] || die "aucune base ${DB_NAME} : lancer 'ensure'"
    mkdir -p "$BACKUP_DIR"; file="${BACKUP_DIR}/amm-import-$(date -u +%Y%m%d-%H%M%S).dump"
    log "pg_dump de la base source -> ${file}"
    pg pg_dump --format=custom --no-owner --no-acl "$src" > "$file"
    restore_into "$file" "$(jq -r .id <<<"$db")"
    point_service_to "$(jq -r .id <<<"$db")"
    ;;
  restore)
    file=${1:?usage : restore <fichier.dump>}
    db=$(db_json); [ -n "$db" ] || die "aucune base ${DB_NAME}"
    restore_into "$file" "$(jq -r .id <<<"$db")"
    point_service_to "$(jq -r .id <<<"$db")"
    ;;
  *) die "commande inconnue : ${cmd}" ;;
esac
