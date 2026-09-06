# AMM INNOV

Plateforme de suivi des **Autorisations de Mise sur le Marché (AMM)** en Afrique.
Elle remplace le classeur Excel `Dashboard AMM Afrique` (15 pays, ~1 550 AMM) par une
application web multi-utilisateurs qui calcule les statuts, alerte **6 mois avant
expiration** (deadline de dépôt), suit le cycle de renouvellement, archive les scans PDF
des autorisations et expose des tableaux de bord temps réel et Grafana.

| Couche | Technologies |
|---|---|
| Frontend | React 19 + TypeScript, Vite, MUI + Data Grid, TanStack Query |
| Backend | Django 5 + DRF, Django Channels (WebSocket), Celery + beat, Daphne |
| Données | PostgreSQL 16, Redis 7, MinIO/S3 (scans PDF) |
| Pilotage | Grafana 12 (vues SQL du schéma `analytics`, rôle lecture seule) |
| Infra | Docker Compose, nginx, Caddy (TLS), GitHub Actions, GHCR |

Documents de référence : [prd.md](prd.md) · [architecture.md](architecture.md) ·
[architecture-essentiels.md](architecture-essentiels.md) · [docs/](docs/)

---

## Prérequis

- Docker Engine ≥ 24 et Docker Compose v2 (`docker compose version`)
- `make` (GNU make)
- 4 Go de RAM libres pour la stack complète
- Optionnel, pour travailler hors Docker : Python 3.12, Node 24

## Démarrage rapide

```bash
git clone <url-du-depot> amm-innov && cd amm-innov
cp .env.example .env
make up            # construit et démarre postgres, redis, backend, worker, beat, frontend, grafana, mailpit
make seed          # comptes et données de démonstration
```

Ou en une commande (crée `.env`, démarre, migre, seed, importe le classeur s'il est dans `data/raw/`) :

```bash
make bootstrap
```

### URLs

| Service | URL | Identifiants |
|---|---|---|
| Application | http://localhost:5173 | comptes de démo ci-dessous |
| API (OpenAPI / Swagger) | http://localhost:8000/api/docs | connecté à http://localhost:8000/admin |
| Grafana | http://localhost:3000 | `admin` / `admin` |
| Mailpit (emails capturés) | http://localhost:8025 | — |
| MinIO console (profil `s3`) | http://localhost:9001 | `minio` / `minio12345` |
| Prometheus (profil `monitoring`) | http://localhost:9090 | — |

### Comptes de démonstration (`make seed`)

| Email | Rôle | Périmètre |
|---|---|---|
| `ceo@amm.local` | `CEO_ADMIN` | CEO / administrateur, tous pays, tous droits |
| `siege@amm.local` | `HQ_REGULATORY` | réglementaire siège, tous pays |
| `senegal@amm.local` | `COUNTRY_REGULATORY` | réglementaire pays, Sénégal et Mali |

Mot de passe commun : `Passw0rd!`

## Import du classeur Excel

Le classeur source (`*.xlsx`) n'est pas versionné (`.gitignore`). Le déposer dans `data/raw/` puis :

```bash
make import FILE="data/raw/Dashboard AMM Afrique 18_08_2026 version 2.1.xlsx"
# Recalculer les statuts à une date de référence (reproduire les totaux du DASHBOARD Excel) :
make import FILE=data/raw/classeur.xlsx TODAY=2026-08-18
```

L'import est idempotent (réimport = mise à jour) et produit un rapport d'anomalies
(dates illisibles, doublons, numéros manquants). Contrôle attendu au 18/08/2026 :
1 548 AMM, 963 valides, 501 expirées, 71 en cours, 13 indéterminées.

## Commandes utiles (`make help`)

| Commande | Effet |
|---|---|
| `make up` / `make down` / `make logs [SERVICE=backend]` | cycle de vie de la stack |
| `make build` | reconstruit les images de dev |
| `make migrate` / `make makemigrations [APP=amm]` | migrations Django |
| `make seed` | données de démonstration |
| `make import FILE=… [TODAY=AAAA-MM-JJ]` | import du classeur |
| `make test-backend [ARGS="-k statut"]` / `make test-frontend` / `make test` | tests |
| `make lint` | ruff, eslint, prettier, tsc |
| `make shell` / `make bash` / `make psql` / `make redis-cli` | consoles |
| `make backup` | `pg_dump` gzip + tar des médias dans `backups/` |
| `make api-schema` / `make api-types` / `make api-check` | schéma OpenAPI, types TypeScript, vérification du contrat |
| `make restore FILE=backups/amm-db-….sql.gz [MEDIA=backups/amm-media-….tar.gz] YES=1` | restauration |
| `make grafana-open` | ouvre Grafana |

Profils Compose optionnels :

```bash
docker compose --profile s3 up -d           # MinIO + bucket amm-documents (DOCUMENT_STORAGE=s3 dans .env)
docker compose --profile monitoring up -d   # Prometheus (scrape de backend:8000/metrics)
```

## Tests et qualité

```bash
make test-backend        # pytest dans le conteneur backend (image de dev, stage `dev` du Dockerfile)
                         # SQLite par défaut ; DATABASE_URL_TEST=postgres://… pour PostgreSQL
make test-frontend       # vitest
make lint                # ruff + eslint + prettier + tsc
```

Contrat API ↔ frontend : le schéma OpenAPI (`backend/schema.yaml`) et les types TypeScript
(`frontend/src/api/schema.d.ts`) sont générés et versionnés ; `frontend/src/api/contract.ts` vérifie à
la compilation que chaque réponse de l'API reste assignable aux types utilisés par l'interface.
Après toute modification d'un serializer : `make api-types` puis commit (`make api-check` rejoue la CI).

La CI GitHub Actions (`.github/workflows/ci.yml`) exécute sur chaque push/PR vers `main` :

1. **backend** : ruff, pytest sur PostgreSQL 16 (`DATABASE_URL_TEST`) avec Redis 7 en service, rapport de couverture, schéma OpenAPI à jour ;
2. **frontend** : eslint/prettier, types générés à jour, `tsc` (contrat API), vitest, build Vite ;
3. **docker** (push sur `main` uniquement) : build du stage `runtime` et push des images
   `ghcr.io/alamine2003/amm-innov-backend` et `…-frontend` taguées `<sha>` et `latest`.
   Les images sont privées par défaut : le workflow Deploy les tire avec `GITHUB_TOKEN`
   (permission `packages: read`) ; pour un `docker pull` manuel sur le serveur, utiliser un token
   personnel `read:packages` ou rendre les packages publics.

Dependabot ne propose que les mises à jour mineures et correctives, regroupées par écosystème ;
les sauts majeurs (MUI, react-router, Django, Python…) se traitent manuellement.

Dependabot (`.github/dependabot.yml`) surveille pip, npm, Docker et GitHub Actions chaque semaine.

## Grafana

Cinq dashboards sont provisionnés depuis `grafana/dashboards/` (dossiers Direction, Réglementaire,
Admin, Exploitation), tous filtrables par pays :

| Dashboard | Public | Contenu |
|---|---|---|
| AMM Afrique — Vue direction | Direction | tableau pays (reprise Excel), compteurs, % valides, répartition statuts/urgences/gammes |
| Pipeline d'expiration | Réglementaire | histogramme mensuel par pays, 50 prochaines échéances, dossiers urgents sans scan |
| Suivi des renouvellements | Réglementaire | entonnoir de workflow, délai moyen de décision, taux de rejet, alertes ouvertes |
| Qualité des données | Admin | indéterminées, dossiers incomplets, scans manquants, lignes à corriger |
| Technique | Exploitation | API, Celery, WebSocket, emails (Prometheus) et PostgreSQL |

Grafana lit la base avec le rôle `grafana_ro` (créé par une migration du backend, mot de passe
`GRAFANA_DB_PASSWORD`) et n'accède qu'au schéma `analytics`. Les alertes métier restent dans
l'application ; l'alerting Grafana est réservé au dashboard technique.

## Déploiement en production

Processus web : `WEB_CONCURRENCY=1` lance Daphne (dev) ; `WEB_CONCURRENCY=N` lance uvicorn avec N workers
(prod, ~80 req/s par worker mesurés, 167 req/s avec 3). Chaque worker a son pool PostgreSQL
(`DB_POOL_MAX_SIZE`) : garder N × pool sous `max_connections`.

### Option retenue : Netlify + Railway

Frontend sur Netlify ([netlify.toml](netlify.toml)), backend, worker Celery, Redis et PostgreSQL sur
Railway ([railway.json](railway.json) pour le service web, [railway.worker.json](railway.worker.json) pour le worker),
scans PDF sur un stockage S3 compatible, Grafana Cloud.
Procédure complète : [docs/deploiement-netlify-railway.md](docs/deploiement-netlify-railway.md).

### Option auto-hébergée : Docker Compose

Un serveur unique (4 vCPU / 8 Go) avec Docker suffit. `docker-compose.prod.yml` utilise les images
GHCR et ajoute **Caddy** (TLS Let's Encrypt automatique, ports 80/443) devant l'image frontend
(nginx : SPA, `/api`, `/ws`, `/grafana/`), ainsi qu'un service `backup` quotidien.

```bash
# Sur le serveur
sudo mkdir -p /opt/amm-innov && cd /opt/amm-innov
# Copier docker-compose.prod.yml, docker/Caddyfile, grafana/, scripts/, .env.example
cp .env.example .env && nano .env      # DOMAIN, ACME_EMAIL, secrets, DJANGO_SETTINGS_MODULE=config.settings.prod
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

Déploiement depuis GitHub : workflow **Deploy** (`.github/workflows/deploy.yml`, déclenchement
manuel, tag d'image en paramètre). Secrets requis : `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`
(et `DEPLOY_PORT` si différent de 22). Il exécute `docker compose pull && up -d` dans `/opt/amm-innov`.

### Première mise en service : éviter le déluge d'alertes

L'historique importé contient plusieurs centaines d'AMM expirées depuis longtemps. Lancer
l'évaluation des règles telle quelle enverrait plus d'un millier d'emails le premier jour.
Deux garde-fous :

1. Après l'import initial, créer les alertes historiques **sans notification** :
   ```bash
   docker compose -f docker-compose.prod.yml exec backend python manage.py evaluate_alerts --quiet
   ```
   Les alertes apparaissent dans l'application et les dashboards ; le passage nocturne suivant
   ne notifie que les nouvelles.
2. En régime permanent, `ALERTS_DISPATCH_MAX_AGE_DAYS` (30 jours par défaut) : une alerte dont
   l'échéance est plus ancienne est créée sans notification, sauf si c'est la plus récente d'une
   AMM encore active (une AMM ajoutée à 100 jours de sa fin reçoit bien son J-180).

Sauvegardes : le service `backup` lance chaque nuit à `BACKUP_HOUR` (02:00 Dakar) un `pg_dump`
compressé et une archive des médias dans `./backups`, rétention `BACKUP_RETENTION_DAYS` (30 jours).
Restauration : `docker compose -f docker-compose.prod.yml run --rm backup /scripts/restore.sh /backups/<fichier>.sql.gz`.
Copier `backups/` hors du serveur (rsync, restic, `mc mirror`) pour une sauvegarde externalisée.

## Structure du dépôt

```
.
├── backend/                 # Django (config/, apps/, tests/, manage.py)
├── frontend/                # React + Vite (src/, vite.config.ts)
├── docker/                  # Dockerfiles, entrypoint, nginx.conf, Caddyfile, prometheus.yml
├── grafana/
│   ├── provisioning/        # datasources (postgres, prometheus) et provider de dashboards
│   └── dashboards/          # direction/, reglementaire/, admin/, exploitation/ (JSON)
├── scripts/                 # backup.sh, restore.sh, dev-bootstrap.sh, wait-for.py
├── data/raw/                # classeur Excel source (hors git)
├── backups/                 # sauvegardes locales (hors git)
├── docs/                    # documentation complémentaire
├── docker-compose.yml       # développement
├── docker-compose.prod.yml  # production
├── Makefile
├── .env.example
├── .github/workflows/       # ci.yml, deploy.yml
├── prd.md                   # cahier des charges
├── architecture.md          # architecture détaillée
└── architecture-essentiels.md
```

## Licence

Projet privé — tous droits réservés.
