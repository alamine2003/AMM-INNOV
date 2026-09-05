# Déploiement : Netlify (frontend) + Render (backend, Redis, PostgreSQL)

Architecture retenue pour la 1.0 :

| Composant | Hébergement | Fichier de configuration |
|---|---|---|
| Frontend React (SPA) | Netlify, CDN, HTTPS automatique | [netlify.toml](../netlify.toml) |
| API + WebSocket (Daphne) | Render, service web Docker | [render.yaml](../render.yaml) |
| Celery worker + beat | Render, background worker Docker (1 instance) | render.yaml |
| Redis (broker, channel layer) | Render Key Value, `noeviction` | render.yaml |
| PostgreSQL 16 | Render Postgres | render.yaml |
| Scans PDF | Stockage S3 compatible externe (Cloudflare R2 conseillé) | variables `S3_*` |
| Grafana | Grafana Cloud (gratuit) branché sur la base Render | dashboards `grafana/dashboards/` |
| Emails | Fournisseur SMTP (Brevo, SendGrid, Resend…) | `EMAIL_URL` |

Le frontend appelle l'API directement sur le domaine Render (CORS), sans proxy Netlify :
les proxys Netlify coupent les requêtes longues, ce qui casserait l'envoi de PDF de 25 Mo
sur une connexion lente.

```mermaid
flowchart LR
    U[Navigateur] -- HTTPS --> N[Netlify<br/>SPA React]
    U -- REST /api/v1 + WebSocket /ws --> R[Render web<br/>Daphne]
    R --> PG[(Render Postgres)]
    R <--> KV[(Render Key Value)]
    W[Render worker<br/>Celery + beat] <--> KV
    W --> PG
    R & W --> S3[(R2 / S3<br/>scans PDF)]
    W -- SMTP --> M[Fournisseur email]
    G[Grafana Cloud] -- lecture seule --> PG
```

Coût indicatif (septembre 2026) : Netlify gratuit, Render web starter 7 $, worker starter 7 $,
Postgres basic 6 $, Key Value gratuit, R2 gratuit sous 10 Go, Grafana Cloud gratuit.
Soit environ **20 $ par mois**. Les plans gratuits Render (web qui s'endort, Postgres qui
expire après 30 jours) conviennent à une démonstration, pas à la production.

---

## 1. Prérequis

- Dépôt GitHub `alamine2003/AMM-INNOV` avec la CI verte sur `main` (Render attend les checks).
- Un compte Render, un compte Netlify, un compte Cloudflare (R2) ou équivalent S3.
- Un fournisseur SMTP et l'URL au format `smtp+tls://utilisateur:motdepasse@hote:587`.
- Le classeur Excel de référence pour l'import initial.

## 1 bis. Un domaine commun pour la session

Le refresh token est un cookie `httpOnly` posé par l'API. Un cookie n'est envoyé au
rafraîchissement que si le frontend et l'API sont sur le **même site** : prévoir un domaine et
deux sous-domaines, par exemple `app.amm-innov.com` (Netlify) et `api.amm-innov.com` (Render), avec
`AUTH_REFRESH_COOKIE_DOMAIN=.amm-innov.com`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
`CSRF_TRUSTED_ORIGINS`, `FRONTEND_URL` et `netlify.toml` ajustés en conséquence.

Pour un essai sur `*.netlify.app` et `*.onrender.com` (deux sites différents), mettre
`AUTH_REFRESH_COOKIE_SAMESITE=None` et laisser le domaine vide : Chrome et Firefox acceptent ce
cookie tiers, Safari le bloque (l'utilisateur est déconnecté au bout de 15 minutes).

## 2. Stockage S3 des scans PDF

Sur Render, le service web (qui reçoit les uploads) et le worker (qui lit les PDF) n'ont
pas de disque partagé : le stockage objet est obligatoire.

1. Créer un bucket privé `amm-documents` (R2 : Cloudflare, R2, Create bucket).
2. Créer un jeton d'API avec lecture et écriture sur ce bucket.
3. Noter `S3_ENDPOINT_URL` (R2 : `https://<account-id>.r2.cloudflarestorage.com`),
   `S3_ACCESS_KEY`, `S3_SECRET_KEY`. `S3_REGION` reste `auto` pour R2.

Les fichiers ne sont jamais servis directement depuis le bucket : l'API vérifie le périmètre
pays puis diffuse le PDF, le bucket peut donc rester entièrement privé.

## 3. Render : créer la stack depuis le Blueprint

1. Render, **New, Blueprint**, choisir le dépôt, branche `main`. Render lit `render.yaml` et
   propose de créer : `amm-innov-backend` (web), `amm-innov-worker`, `amm-innov-redis`,
   `amm-innov-db` et le groupe de variables `amm-innov-shared`.
2. Renseigner les variables marquées `sync: false` :

   | Variable | Valeur |
   |---|---|
   | `DJANGO_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
   | `EMAIL_URL` | URL SMTP du fournisseur |
   | `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | étape 2 |
   | `GRAFANA_DB_PASSWORD` | mot de passe du rôle `grafana_ro` (étape 6) |

3. Si le nom du service web n'est pas `amm-innov-backend`, corriger `ALLOWED_HOSTS` et
   `CSRF_TRUSTED_ORIGINS` dans le groupe, ainsi que les deux URL dans `netlify.toml`.
4. Lancer la création. Le premier déploiement construit l'image Docker (5 à 8 minutes),
   applique les migrations et collecte les statiques (entrypoint). Vérifier
   `https://amm-innov-backend.onrender.com/api/v1/health` : `{"status":"ok","database":true,"redis":true}`.
5. Créer le premier compte administrateur depuis le **Shell** du service web :
   ```bash
   python manage.py createsuperuser
   ```

Remarques :

- `WEB_CONCURRENCY=1` sur le plan starter (512 Mo de RAM : un second worker uvicorn risquerait
  l'arrêt pour mémoire insuffisante). Dès le plan standard (2 Go), `WEB_CONCURRENCY=2` puis 1 worker
  par 0,5 CPU environ, en gardant `WEB_CONCURRENCY × DB_POOL_MAX_SIZE` sous la limite de
  connexions du plan Postgres (97 sur basic-256mb).
- Si le nom `amm-innov-backend` est déjà pris, Render en attribue un autre : l'API l'accepte
  automatiquement (`RENDER_EXTERNAL_HOSTNAME`), mais il faut le reporter dans `netlify.toml`
  (`VITE_API_BASE`, `VITE_WS_URL`).
- Le WebSocket accepte les origines de `CORS_ALLOWED_ORIGINS` : le site Netlify doit y figurer.
- Le worker tourne avec beat intégré (`celery worker -B`) : **ne jamais passer `numInstances`
  au-dessus de 1**, sinon les jobs nocturnes s'exécutent en double.
- `autoDeployTrigger: checksPass` : Render redéploie à chaque push sur `main` **après** la CI verte.
- Domaine personnalisé : Render, service web, Settings, Custom Domains (ex. `api.amm-innov.com`),
  puis ajouter ce domaine dans `ALLOWED_HOSTS` et `CSRF_TRUSTED_ORIGINS`.

## 4. Netlify : déployer le frontend

1. Netlify, **Add new site, Import an existing project**, choisir le dépôt. Netlify lit
   `netlify.toml` : base `frontend`, build `npm ci && npm run build`, publication `dist`,
   Node 24, et les deux variables `VITE_API_BASE` et `VITE_WS_URL` pointant vers Render.
2. Site name : `amm-innov` (donne `https://amm-innov.netlify.app`). Si un autre nom ou un
   domaine personnalisé est utilisé, mettre à jour `CORS_ALLOWED_ORIGINS` et `FRONTEND_URL`
   côté Render (les liens des emails d'alerte utilisent `FRONTEND_URL`).
3. Déployer. Se connecter avec le superutilisateur créé à l'étape 3.5, puis créer les
   comptes siège et pays dans Administration, Utilisateurs.

Netlify déploie à chaque push sur `main`, sans attendre la CI : pour l'aligner, activer
« Deploy only when checks pass » dans Site configuration, Build & deploy (ou déclencher
le build depuis GitHub via un *build hook* après le job CI).

## 5. Mise en service des données

Depuis le Shell Render du service web :

```bash
# 1. Référentiels et règles d'alerte par défaut
python manage.py seed_alert_rules

# 2. Import du classeur (le déposer d'abord via le shell : curl -o /tmp/classeur.xlsx <url signée>)
python manage.py import_excel /tmp/classeur.xlsx --user admin@votre-domaine.com

# 3. Alertes historiques SANS notification (évite plus d'un millier d'emails le premier jour)
python manage.py evaluate_alerts --quiet
```

Le passage nocturne (00:15 Dakar) ne notifiera ensuite que les nouvelles alertes.
Ne pas lancer `seed_demo` en production : il crée des comptes avec un mot de passe connu.

## 6. Grafana Cloud

1. Créer une stack gratuite sur grafana.com.
2. Render, base `amm-innov-db`, **Access Control** : autoriser les IP sortantes de Grafana Cloud
   (listées dans Grafana, Connections, Data sources, PostgreSQL, « Allowed IPs »).
3. Data source PostgreSQL : hôte et port de l'**External Database URL** Render, base `amm`,
   utilisateur `grafana_ro`, mot de passe `GRAFANA_DB_PASSWORD`, TLS `require`.
   Le rôle `grafana_ro` est créé par la migration `analytics` avec accès au seul schéma `analytics`.
   Si la migration n'a pas pu le créer (privilèges Render), le créer via `psql` sur l'URL externe :
   ```sql
   CREATE ROLE grafana_ro LOGIN PASSWORD '<GRAFANA_DB_PASSWORD>';
   GRANT USAGE ON SCHEMA analytics TO grafana_ro;
   GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO grafana_ro;
   ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO grafana_ro;
   ```
4. Importer les cinq dashboards JSON de `grafana/dashboards/` (Dashboards, New, Import) en
   sélectionnant cette source de données. Le dashboard « Technique » a besoin de Prometheus ;
   Grafana Cloud fournit un Prometheus hébergé qui peut scraper `/metrics` du backend
   (renseigner `METRICS_TOKEN` côté Render et le même jeton en « Bearer » dans la configuration du scrape).

## 7. Sauvegardes

Render Postgres (plans payants) conserve des sauvegardes quotidiennes pendant 7 jours.
Pour une copie externalisée, depuis n'importe quelle machine avec Docker :

```bash
docker run --rm -e PGPASSWORD='<mot de passe>' postgres:16 \
  pg_dump -h <hote-externe-render> -U amm -d amm --no-owner | gzip > amm-db-$(date +%Y%m%d).sql.gz
```

Les scans PDF sont dans le bucket S3 : activer le versionnement du bucket, ou le répliquer
(`rclone sync`), suffit.

## 8. Vérifications après déploiement

- `GET /api/v1/health` renvoie `database: true, redis: true`.
- Connexion sur Netlify, l'indicateur temps réel passe à « connecté » (WebSocket direct vers Render).
- Envoi d'un PDF depuis une fiche AMM, puis ouverture dans la visionneuse (stockage S3).
- Render, worker, logs : `celery@… ready` et `beat: Starting…`, puis à 00:05 Dakar
  `recompute_all_statuses` et à 00:15 `evaluate_alert_rules`.
- Un email d'alerte de test arrive (créer une AMM à 100 jours de sa fin).

## 9. Ce qui ne s'applique plus

`docker-compose.prod.yml`, `docker/Caddyfile` et le workflow GitHub **Deploy** (SSH) restent
disponibles pour un serveur unique auto-hébergé ; ils ne sont pas utilisés avec Netlify + Render.
