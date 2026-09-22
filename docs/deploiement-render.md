# Déploiement : Netlify (frontend) + Render gratuit (backend)

Remplace Railway (septembre 2026, fin du crédit). Tout le backend tient dans l'offre gratuite.

| Composant | Hébergement | Configuration |
|---|---|---|
| Frontend React | Netlify (gratuit) | [netlify.toml](../netlify.toml), job `netlify` de la CI |
| API + WebSocket + Celery (beat intégré) | Render, service web Docker gratuit `amm-innov-api`, `AMM_ROLE=all` | [render.yaml](../render.yaml) |
| Redis (broker, channel layer, cache) | Render Key Value gratuit `amm-innov-redis` (25 Mo, `noeviction`) | [render.yaml](../render.yaml) |
| PostgreSQL 16 | Render Postgres gratuit `amm-innov-db` (1 Go) | [scripts/render_db.sh](../scripts/render_db.sh), workflow **Base Render** |
| Sauvegardes | Artefacts GitHub Actions (90 jours), à télécharger sur le poste admin | [.github/workflows/render-db.yml](../.github/workflows/render-db.yml) |

## Les limites de l'offre gratuite, et ce qui les compense

- **La base est supprimée 30 jours après sa création** (une seule base gratuite par compte).
  Le workflow *Base Render* tourne chaque nuit : sauvegarde, puis, dès 25 jours, renouvellement
  complet — sauvegarde vérifiée, suppression de l'ancienne, création, restauration, nouvelle
  `DATABASE_URL`, redéploiement. Coupure : 3 à 5 minutes, la nuit. Si une étape échoue, la
  sauvegarde reste dans les artefacts du run et `scripts/render_db.sh restore` la remet en place.
- **L'API s'endort après 15 minutes sans requête** (réveil ~50 s) et Celery s'endort avec elle.
  Le workflow *Réveil API* l'appelle toutes les 10 minutes (un service éveillé en permanence =
  720 h/mois, sous les 750 h gratuites). GitHub suspend les workflows planifiés d'un dépôt sans
  commit depuis 60 jours : un e-mail prévient, un clic les réactive.
- **Disque éphémère** : un fichier écrit sur le conteneur disparaît au redéploiement ou au réveil.
  Les imports (classeur, dossier) sont traités dans le même conteneur, donc sans problème. Les
  **scans PDF**, eux, doivent aller sur un stockage S3 pour être conservés : section 4.
- 512 Mo de mémoire pour le web et Celery (mesuré ~240 Mo le web, ~200 Mo Celery à 1 processus).

## 1. Créer les services (une fois)

1. Render, **New, Blueprint**, dépôt `alamine2003/AMM-INNOV`, branche `main` : Render lit
   `render.yaml` et crée `amm-innov-api` et `amm-innov-redis`. Laisser vides les variables
   `sync: false` demandées (Gmail, superutilisateur) si on ne les a pas sous la main.
2. Render, **Account settings, API keys** : créer une clé. GitHub, dépôt, **Settings, Secrets and
   variables, Actions** : secret `RENDER_API_KEY`.
3. GitHub, **Actions, Base Render, Run workflow**, action `ensure` : crée `amm-innov-db`, pose
   `DATABASE_URL` sur l'API et la redéploie (les migrations s'appliquent au démarrage).
4. Vérifier `https://amm-innov-api.onrender.com/api/v1/health` :
   `{"status":"ok","database":true,"redis":true,...}`.

## 2. Reprendre les données de Railway (une fois, avant l'arrêt de Railway)

1. Railway, service Postgres, **Settings, Networking, TCP Proxy** activé, puis onglet
   **Variables** : copier `DATABASE_PUBLIC_URL`.
2. GitHub, secret `SOURCE_DATABASE_URL` = cette URL.
3. **Actions, Base Render, Run workflow**, action `import-railway` : dump Railway, restauration
   dans Render, redéploiement. Le dump reste en artefact.
4. Contrôler dans l'application (nombre d'AMM, derniers renouvellements), puis supprimer le
   secret `SOURCE_DATABASE_URL` et le projet Railway.

## 3. Sauvegardes sur le poste admin

Chaque run du workflow *Base Render* publie la sauvegarde (`amm-render-AAAAMMJJ-HHMMSS.dump`,
format `pg_dump -Fc`) en artefact, gardée 90 jours : **Actions, Base Render**, dernier run,
**Artifacts**, télécharger. Pour la remettre en place :

```bash
RENDER_API_KEY=... scripts/render_db.sh restore amm-render-20261020-023000.dump
```

(depuis Linux ou la CI ; sur macOS, lancer le workflow, ou `docker run` l'image `postgres:16`.)

Actions manuelles : `status`, `backup`, `rotate-force` (renouveler tout de suite).

## 4. Scans PDF : stockage S3 gratuit (recommandé)

Tant que `DOCUMENT_STORAGE=local`, un scan déposé est perdu au prochain redéploiement. Pour le
conserver, un bucket privé **Cloudflare R2** (10 Go gratuits) :
variables de `amm-innov-api` `DOCUMENT_STORAGE=s3`, `S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`,
`S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION=auto`, `S3_ADDRESSING_STYLE=path`.

## 5. E-mails

Render gratuit bloque aussi les ports SMTP sortants : garder l'API Gmail (`EMAIL_URL=gmail://`,
`GMAIL_*`, voir [deploiement-netlify-railway.md](deploiement-netlify-railway.md), étape 2 bis).

## 6. Frontend

`netlify.toml` pointe sur `amm-innov-api.onrender.com`. Si Render attribue un autre nom (suffixe),
corriger `VITE_API_BASE` et `VITE_WS_URL` puis pousser : la CI republie Netlify. Le cookie de
session passe entre `*.netlify.app` et `*.onrender.com` avec `AUTH_REFRESH_COOKIE_SAMESITE=None`
(Safari le bloque : prévoir un domaine commun, voir l'ancien guide, étape 1 bis).
