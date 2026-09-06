# ---------------------------------------------------------------------------
# AMM INNOV — raccourcis de développement et d'exploitation
#   make help
# ---------------------------------------------------------------------------
SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      ?= docker compose
COMPOSE_PROD ?= docker compose -f docker-compose.prod.yml
BACKEND_EXEC := $(COMPOSE) exec backend
FRONTEND_EXEC:= $(COMPOSE) exec frontend
GRAFANA_URL  ?= http://localhost:3000
# make import FILE=data/raw/classeur.xlsx [TODAY=2026-08-18]
FILE ?=
TODAY ?=
IMPORT_ARGS := $(if $(TODAY),--today $(TODAY),)

.PHONY: help up down stop restart ps logs build pull migrate makemigrations seed import \
        test-backend test-frontend test lint lint-backend lint-frontend shell psql redis-cli \
        backup restore grafana-open bootstrap clean prod-up prod-down prod-pull prod-logs env

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

env: ## Crée .env depuis .env.example s'il n'existe pas
	@test -f .env || (cp .env.example .env && echo ".env créé depuis .env.example")

# ---------------- Cycle de vie ----------------
up: env ## Démarre la stack de développement (détachée)
	$(COMPOSE) up -d --build

down: ## Arrête et supprime les conteneurs (les volumes sont conservés)
	$(COMPOSE) down --remove-orphans

stop: ## Arrête les conteneurs sans les supprimer
	$(COMPOSE) stop

restart: ## Redémarre backend, worker et beat
	$(COMPOSE) restart backend worker beat

ps: ## État des services
	$(COMPOSE) ps

logs: ## Suit les logs (SERVICE=backend pour filtrer)
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

build: ## Reconstruit les images de développement
	$(COMPOSE) build --pull

pull: ## Récupère les images de base
	$(COMPOSE) pull --ignore-buildable

# ---------------- Base de données / données ----------------
migrate: ## Applique les migrations Django
	$(BACKEND_EXEC) python manage.py migrate --noinput

makemigrations: ## Génère les migrations (APP=nom optionnel)
	$(BACKEND_EXEC) python manage.py makemigrations $(APP)

seed: ## Charge les données de démonstration (comptes ceo/siege/senegal@amm.local)
	$(BACKEND_EXEC) python manage.py seed_demo

import: ## Importe un classeur Excel : make import FILE=data/raw/x.xlsx [TODAY=AAAA-MM-JJ]
	@test -n "$(FILE)" || (echo "Usage : make import FILE=chemin/vers/classeur.xlsx [TODAY=AAAA-MM-JJ]" && exit 1)
	@test -f "$(FILE)" || (echo "Fichier introuvable : $(FILE)" && exit 1)
	$(COMPOSE) cp "$(FILE)" backend:/tmp/import.xlsx
	$(BACKEND_EXEC) python manage.py import_excel /tmp/import.xlsx $(IMPORT_ARGS)

# ---------------- Qualité ----------------
test-backend: ## Tests backend (pytest, SQLite par défaut)
	$(COMPOSE) exec -e DJANGO_SETTINGS_MODULE=config.settings.test backend pytest -q $(ARGS)

test-frontend: ## Tests frontend (vitest)
	$(FRONTEND_EXEC) npm run test -- --run

test: test-backend test-frontend ## Tous les tests

lint-backend: ## ruff
	$(BACKEND_EXEC) ruff check .

lint-frontend: ## eslint + prettier + tsc
	$(FRONTEND_EXEC) npm run lint
	$(FRONTEND_EXEC) npm run typecheck

lint: lint-backend lint-frontend ## Tous les linters

deploy-frontend: ## Construit et publie le frontend sur Netlify (production), d'après netlify.toml
	npx --no-install netlify deploy --build --prod --message "AMM INNOV $$(git rev-parse --short HEAD)"

api-schema: ## Régénère backend/schema.yaml (OpenAPI) depuis le code Django (sur PostgreSQL : les bornes d'entiers diffèrent sous SQLite)
	$(BACKEND_EXEC) python manage.py spectacular --file /tmp/schema.yaml --validate
	$(COMPOSE) cp backend:/tmp/schema.yaml backend/schema.yaml

api-types: api-schema ## Régénère frontend/src/api/schema.d.ts depuis le schéma OpenAPI
	$(FRONTEND_EXEC) npm run api:types

api-check: api-types ## Vérifie que le contrat API/frontend est à jour et cohérent (CI locale)
	git diff --exit-code -- backend/schema.yaml frontend/src/api/schema.d.ts
	$(FRONTEND_EXEC) npm run typecheck

# ---------------- Accès interactifs ----------------
shell: ## Shell Django (shell_plus si disponible)
	$(BACKEND_EXEC) sh -c 'python manage.py shell_plus 2>/dev/null || python manage.py shell'

bash: ## Bash dans le conteneur backend
	$(BACKEND_EXEC) bash

psql: ## Console psql sur la base amm
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-amm} -d $${POSTGRES_DB:-amm}

redis-cli: ## Console redis
	$(COMPOSE) exec redis redis-cli

# ---------------- Sauvegardes ----------------
backup: ## pg_dump gzip + tar des médias dans ./backups (rétention 30 j)
	@mkdir -p backups
	$(COMPOSE) run --rm backup /scripts/backup.sh

restore: ## Restaure une sauvegarde : make restore FILE=backups/amm-db-AAAAMMDD-HHMMSS.sql.gz
	@test -n "$(FILE)" || (echo "Usage : make restore FILE=backups/amm-db-....sql.gz [MEDIA=backups/amm-media-....tar.gz]" && exit 1)
	$(COMPOSE) run --rm -e RESTORE_YES=$(YES) backup /scripts/restore.sh /$(FILE) $(if $(MEDIA),/$(MEDIA),)

# ---------------- Divers ----------------
grafana-open: ## Ouvre Grafana dans le navigateur
	@(open $(GRAFANA_URL) 2>/dev/null || xdg-open $(GRAFANA_URL) 2>/dev/null || echo "Grafana : $(GRAFANA_URL)")

bootstrap: ## up + migrate + seed + import du classeur présent dans data/raw/
	./scripts/dev-bootstrap.sh

clean: ## Supprime conteneurs ET volumes (données perdues !)
	$(COMPOSE) down --remove-orphans --volumes

# ---------------- Production ----------------
prod-pull: ## Récupère les images GHCR (TAG=…)
	$(COMPOSE_PROD) pull

prod-up: ## Démarre la stack de production
	$(COMPOSE_PROD) up -d --remove-orphans

prod-down: ## Arrête la stack de production
	$(COMPOSE_PROD) down --remove-orphans

prod-logs: ## Logs de production
	$(COMPOSE_PROD) logs -f --tail=200 $(SERVICE)
