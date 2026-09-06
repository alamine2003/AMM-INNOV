# Déploiement : Netlify (frontend) + Railway (backend, Redis, PostgreSQL)

Architecture retenue pour la 1.0 :

| Composant | Hébergement | Fichier de configuration |
|---|---|---|
| Frontend React (SPA) | Netlify, CDN, HTTPS automatique | [netlify.toml](../netlify.toml) |
| API + WebSocket | Railway, service Docker `amm-innov-backend` | [railway.json](../railway.json) |
| Celery worker + beat | Railway, service Docker `amm-innov-worker` (1 réplique), variable `AMM_ROLE=worker` | [railway.json](../railway.json) |
| Redis (broker, channel layer, cache) | Railway, service Redis | variables de référence |
| PostgreSQL 16 | Railway, service Postgres | variables de référence |
| Scans PDF | Stockage S3 compatible externe (Cloudflare R2 conseillé) | variables `S3_*` |
| Grafana | Grafana Cloud (gratuit) branché sur la base Railway (proxy TCP) | dashboards `grafana/dashboards/` |
| Emails | Fournisseur SMTP (Brevo, SendGrid, Resend…) | `EMAIL_URL` |

Le frontend appelle l'API directement sur le domaine Railway (CORS), sans proxy Netlify :
les proxys Netlify coupent les requêtes longues, ce qui casserait l'envoi de PDF de 25 Mo
sur une connexion lente.

```mermaid
flowchart LR
    U[Navigateur] -- HTTPS --> N[Netlify<br/>SPA React]
    U -- REST /api/v1 + WebSocket /ws --> R[Railway web<br/>Daphne / uvicorn]
    R --> PG[(Railway Postgres)]
    R <--> KV[(Railway Redis)]
    W[Railway worker<br/>Celery + beat] <--> KV
    W --> PG
    R & W --> S3[(R2 / S3<br/>scans PDF)]
    W -- SMTP --> M[Fournisseur email]
    G[Grafana Cloud] -- lecture seule, proxy TCP --> PG
```

Coût indicatif (septembre 2026) : Railway plan Hobby 5 $ par mois incluant 5 $ d'usage, puis
facturation à la ressource (mémoire, CPU, disque, sortie réseau). Pour cette application :
web ~0,5 Go, worker ~0,3 Go, Postgres et Redis ~0,3 Go, soit **10 à 15 $ par mois** au total.
Netlify gratuit, R2 gratuit sous 10 Go, Grafana Cloud gratuit. Le plan Trial de Railway
(crédit unique) suffit pour une démonstration, pas pour la production (services arrêtés à
épuisement du crédit).

---

## 1. Prérequis

- Dépôt GitHub `alamine2003/AMM-INNOV` avec la CI verte sur `main`.
- Un compte Railway (plan Hobby), un compte Netlify, un compte Cloudflare (R2) ou équivalent S3.
- Un fournisseur SMTP et l'URL au format `smtp+tls://utilisateur:motdepasse@hote:587`.
- Le classeur Excel de référence pour l'import initial.

## 1 bis. Un domaine commun pour la session

Le refresh token est un cookie `httpOnly` posé par l'API. Un cookie n'est envoyé au
rafraîchissement que si le frontend et l'API sont sur le **même site** : prévoir un domaine et
deux sous-domaines, par exemple `app.amm-innov.com` (Netlify) et `api.amm-innov.com` (Railway,
Settings, Networking, Custom Domain), avec `AUTH_REFRESH_COOKIE_DOMAIN=.amm-innov.com`,
`AUTH_REFRESH_COOKIE_SAMESITE=Lax`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
`CSRF_TRUSTED_ORIGINS`, `FRONTEND_URL` et `netlify.toml` ajustés en conséquence.

Pour un essai sur `*.netlify.app` et `*.up.railway.app` (deux sites différents), mettre
`AUTH_REFRESH_COOKIE_SAMESITE=None` et laisser le domaine vide : Chrome et Firefox acceptent ce
cookie tiers, Safari le bloque (l'utilisateur est déconnecté au bout de 15 minutes).

## 2. Stockage S3 des scans PDF

Sur Railway, le service web (qui reçoit les uploads) et le worker (qui lit les PDF) n'ont
pas de disque partagé : le stockage objet est obligatoire.

1. Créer un bucket privé `amm-documents` (R2 : Cloudflare, R2, Create bucket).
2. Créer un jeton d'API avec lecture et écriture sur ce bucket.
3. Noter `S3_ENDPOINT_URL` (R2 : `https://<account-id>.r2.cloudflarestorage.com`),
   `S3_ACCESS_KEY`, `S3_SECRET_KEY`. `S3_REGION` reste `auto` pour R2.

Les fichiers ne sont jamais servis directement depuis le bucket : l'API vérifie le périmètre
pays puis diffuse le PDF, le bucket peut donc rester entièrement privé.

## 3. Railway : créer le projet

Railway ne lit pas de fichier de variables : `railway.json` décrit le build et le démarrage
d'un service, les variables se saisissent dans le tableau de bord (ou avec la CLI,
`railway variables --set`). Un projet, quatre services.

### 3.1 Base et Redis

1. Railway, **New Project**, **Deploy PostgreSQL**. Dans le service Postgres, Settings,
   **TCP Proxy** : à activer plus tard pour Grafana Cloud et les sauvegardes (étapes 6 et 7).
2. Dans le projet, **+ New, Database, Redis**.

### 3.2 Service web `amm-innov-backend`

1. **+ New, GitHub Repo**, choisir `AMM-INNOV`, branche `main`. Railway détecte
   `railway.json` : build Docker avec `docker/backend.Dockerfile` (contexte = racine du dépôt,
   `.dockerignore` respecté), démarrage `entrypoint.sh serve`, sonde `/api/v1/health`.
   Laisser **Root Directory** vide (racine du dépôt) : le Dockerfile copie `backend/` et `docker/`.
   La variable `RAILWAY_DOCKERFILE_PATH=docker/backend.Dockerfile` force ce build même si
   Railway a d'abord détecté le projet autrement.
2. Settings, **Networking, Generate Domain** : Railway propose un domaine
   `amm-innov-backend-production-xxxx.up.railway.app`, renommable (par exemple
   `amm-innov-backend.up.railway.app` s'il est libre). Le port demandé est celui de la variable
   `PORT` ; laisser Railway le fixer.
3. Settings, **Deploy, Wait for CI** : cocher, pour ne déployer qu'après la CI GitHub verte.
4. Variables (onglet **Variables**, bouton **Raw Editor** pour coller le bloc) :

   ```
   DJANGO_SETTINGS_MODULE=config.settings.prod
   DJANGO_SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(64))">
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   REDIS_URL=${{Redis.REDIS_URL}}
   BIND_HOST=::
   WEB_CONCURRENCY=1
   NUM_PROXIES=1
   ALLOWED_HOSTS=amm-innov-backend.up.railway.app
   CORS_ALLOWED_ORIGINS=https://amm-innov.netlify.app
   CSRF_TRUSTED_ORIGINS=https://amm-innov-backend.up.railway.app
   FRONTEND_URL=https://amm-innov.netlify.app
   AUTH_REFRESH_COOKIE_SAMESITE=None
   AUTH_REFRESH_COOKIE_DOMAIN=
   TIME_ZONE=Africa/Dakar
   EMAIL_URL=smtp+tls://utilisateur:motdepasse@smtp.fournisseur.tld:587
   DEFAULT_FROM_EMAIL=AMM INNOV <no-reply@amm-innov.com>
   DOCUMENT_STORAGE=s3
   S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
   S3_BUCKET=amm-documents
   S3_ACCESS_KEY=<jeton R2>
   S3_SECRET_KEY=<secret R2>
   S3_REGION=auto
   DOCUMENT_MAX_MB=25
   ALERTS_DISPATCH_MAX_AGE_DAYS=30
   DB_POOL_MAX_SIZE=20
   GRAFANA_DB_PASSWORD=<mot de passe du rôle grafana_ro>
   METRICS_TOKEN=<jeton du scrape Prometheus, optionnel>
   WAIT_TIMEOUT=120
   ```

   `${{Postgres.DATABASE_URL}}` et `${{Redis.REDIS_URL}}` sont des **références** Railway : elles
   pointent vers le réseau privé (`postgres.railway.internal`, IPv6), d'où `BIND_HOST=::`.
   L'hôte public attribué (`RAILWAY_PUBLIC_DOMAIN`) et l'hôte privé sont acceptés d'office par
   l'API ; `ALLOWED_HOSTS` sert surtout pour un domaine personnalisé.
5. Déployer. Le premier déploiement construit l'image (4 à 6 minutes), applique les migrations
   et collecte les statiques (entrypoint). Vérifier
   `https://<domaine>/api/v1/health` : `{"status":"ok","database":true,"redis":true}`.
6. Créer le premier compte administrateur (CLI Railway, depuis le dépôt) :
   ```bash
   railway login && railway link            # choisir le projet et le service amm-innov-backend
   railway run python manage.py createsuperuser
   ```
   (`railway run` exécute la commande localement avec les variables du service ; la base est
   joignable via le proxy TCP, ou utiliser `railway ssh` pour un shell dans le conteneur.)

### 3.3 Service worker `amm-innov-worker`

1. **+ New, GitHub Repo**, le même dépôt : même `railway.json`, même image.
2. Variables : les mêmes que le service web (Raw Editor, coller le même bloc) **plus**
   `AMM_ROLE=worker` (l'entrypoint lance alors Celery avec beat intégré au lieu du serveur web),
   `RUN_MIGRATIONS=0`, `COLLECT_STATIC=0`, `DB_POOL_MAX_SIZE=4`. Ne pas générer de domaine.
3. **Une seule réplique** : beat est intégré au worker, deux répliques exécuteraient les jobs
   nocturnes en double.

Le worker attend que le service web ait appliqué les migrations avant de démarrer (entrypoint).

### 3.4 Remarques

- Mémoire : mesuré 236 Mo pour deux workers uvicorn à vide, 235 Mo pour un processus sous
  charge. `WEB_CONCURRENCY=2` est raisonnable sur Railway (mémoire facturée à l'usage, pas de
  plafond dur sur Hobby) ; garder `WEB_CONCURRENCY × DB_POOL_MAX_SIZE` sous la limite de
  connexions Postgres (100 par défaut).
- Le WebSocket accepte les origines de `CORS_ALLOWED_ORIGINS` : le site Netlify doit y figurer.
- Redéploiement : à chaque push sur `main` (après la CI si « Wait for CI » est coché).
- Domaine personnalisé : Settings, Networking, Custom Domain (`api.amm-innov.com`) puis
  variables de l'étape 1 bis.

## 4. Netlify : déployer le frontend

1. Netlify, **Add new site, Import an existing project**, choisir le dépôt. Netlify lit
   `netlify.toml` : base `frontend`, build `npm ci && npm run build`, publication `dist`,
   Node 24, et les deux variables `VITE_API_BASE` et `VITE_WS_URL`.
2. **Reporter le domaine Railway** de l'étape 3.2.2 dans `netlify.toml` (`VITE_API_BASE`,
   `VITE_WS_URL`) si ce n'est pas `amm-innov-backend.up.railway.app`, ou le saisir dans
   Site configuration, Environment variables (prioritaire sur le fichier).
3. Site name : `amm-innov` (donne `https://amm-innov.netlify.app`). Si un autre nom ou un
   domaine personnalisé est utilisé, mettre à jour `CORS_ALLOWED_ORIGINS` et `FRONTEND_URL`
   côté Railway (les liens des emails d'alerte utilisent `FRONTEND_URL`).
4. Déployer. Se connecter avec le superutilisateur créé à l'étape 3.2.6, puis créer les
   comptes siège et pays dans Administration, Utilisateurs.

Netlify déploie à chaque push sur `main`, sans attendre la CI : pour l'aligner, activer
« Deploy only when checks pass » dans Site configuration, Build & deploy (ou déclencher
le build depuis GitHub via un *build hook* après le job CI).

## 5. Mise en service des données

Depuis un shell dans le conteneur web (`railway ssh`, service `amm-innov-backend`) :

```bash
# 1. Référentiels et règles d'alerte par défaut
python manage.py seed_alert_rules

# 2. Import du classeur : d'abord le déposer dans le conteneur (curl -o /tmp/classeur.xlsx <url signée>),
#    ou le téléverser depuis l'application (Administration, Imports, case « Simulation » pour un
#    premier passage à blanc)
python manage.py import_excel /tmp/classeur.xlsx --user admin@votre-domaine.com --dry-run
python manage.py import_excel /tmp/classeur.xlsx --user admin@votre-domaine.com

# 3. Doublons de produits issus du classeur : fusion des groupes sans conflit
python manage.py product_duplicates --merge

# 4. Alertes historiques SANS notification (évite plus d'un millier d'emails le premier jour)
python manage.py evaluate_alerts --quiet
```

Le passage nocturne (00:15 Dakar) ne notifiera ensuite que les nouvelles alertes.
Ne pas lancer `seed_demo` en production : il crée des comptes avec un mot de passe connu.

## 6. Grafana Cloud

1. Créer une stack gratuite sur grafana.com.
2. Railway, service Postgres, Settings, **TCP Proxy** : activer ; Railway donne un hôte et un
   port publics (`xxx.proxy.rlwy.net:NNNNN`). La base reste protégée par mot de passe ;
   utiliser le rôle `grafana_ro` (lecture seule sur le schéma `analytics`), jamais le compte
   principal.
3. Data source PostgreSQL : cet hôte et ce port, base `railway`, utilisateur `grafana_ro`, mot
   de passe `GRAFANA_DB_PASSWORD`, TLS `require`. Le rôle `grafana_ro` est créé par la migration
   `analytics`. Si elle n'a pas pu le créer (privilèges), le créer via `psql` sur le proxy TCP :
   ```sql
   CREATE ROLE grafana_ro LOGIN PASSWORD '<GRAFANA_DB_PASSWORD>';
   GRANT USAGE ON SCHEMA analytics TO grafana_ro;
   GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO grafana_ro;
   ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO grafana_ro;
   ```
4. Importer les cinq dashboards JSON de `grafana/dashboards/` (Dashboards, New, Import) en
   sélectionnant cette source de données. Le dashboard « Technique » a besoin de Prometheus ;
   Grafana Cloud fournit un Prometheus hébergé qui peut scraper `/metrics` du backend
   (renseigner `METRICS_TOKEN` côté Railway et le même jeton en « Bearer » dans la configuration
   du scrape).

## 7. Sauvegardes

Railway conserve des sauvegardes de Postgres (quotidiennes sur le plan Pro ; sur Hobby, vérifier
l'offre en vigueur). Pour une copie externalisée, via le proxy TCP, depuis n'importe quelle
machine avec Docker :

```bash
docker run --rm -e PGPASSWORD='<mot de passe>' postgres:16 \
  pg_dump -h <hote>.proxy.rlwy.net -p <port> -U postgres -d railway --no-owner \
  | gzip > amm-db-$(date +%Y%m%d).sql.gz
```

Les scans PDF sont dans le bucket S3 : activer le versionnement du bucket, ou le répliquer
(`rclone sync`), suffit.

## 8. Vérifications après déploiement

- `GET /api/v1/health` renvoie `database: true, redis: true`.
- Connexion sur Netlify, l'indicateur temps réel passe à « connecté » (WebSocket direct vers Railway).
- Envoi d'un PDF depuis une fiche AMM, puis ouverture dans la visionneuse (stockage S3).
- Railway, service worker, logs : `celery@… ready` et `beat: Starting…`, puis à 00:05 Dakar
  `recompute_all_statuses` et à 00:15 `evaluate_alert_rules`.
- Un email d'alerte de test arrive (créer une AMM à 100 jours de sa fin).

## 9. Ce qui ne s'applique plus

`docker-compose.prod.yml`, `docker/Caddyfile` et le workflow GitHub **Deploy** (SSH) restent
disponibles pour un serveur unique auto-hébergé ; ils ne sont pas utilisés avec Netlify + Railway.
