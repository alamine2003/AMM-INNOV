# Changelog

Toutes les évolutions notables du projet sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement [SemVer](https://semver.org/lang/fr/).

## [Non publié]

### Ajouté
- Déploiement Netlify + Render : `netlify.toml`, `render.yaml`, guide `docs/deploiement-netlify-render.md`.
- Revue complète du 5 septembre 2026 (`docs/rapport-revue-2026-09-05.md`) : tests de charge à 30, 60 et
  100 utilisateurs, tests de concurrence, durcissement (voir « Corrigé » et « Sécurité »).
- Pool de connexions PostgreSQL (psycopg, `DB_POOL_MAX_SIZE`) : sans lui, l'API saturait PostgreSQL
  (« too many clients ») dès 30 utilisateurs simultanés sous ASGI.
- `/metrics` protégé par `METRICS_TOKEN` (optionnel) ; `NUM_PROXIES` pour lire la vraie IP cliente.

### Sécurité
- Couverture pays d'un produit : un réglementaire pays ne voit plus le statut des autres pays.
- Assignation d'une alerte limitée aux utilisateurs ayant accès au pays de l'alerte.
- Statut d'un renouvellement modifiable uniquement via `/renewals/{id}/transition` (plus de PATCH direct).
- Throttle de connexion par IP (30/min) **et** par compte visé (10/min) ; validateurs de mot de passe
  complétés (similarité avec l'email, mots de passe numériques) ; `defusedxml` pour les classeurs importés.

### Corrigé
- Courses de concurrence : création de deux renouvellements ouverts, transitions simultanées sur un même
  renouvellement, doublons de scan sous envois simultanés (verrous de ligne + contrainte d'unicité
  `(amm, sha256)` tant que le document n'est pas archivé).
- Export Excel/CSV : mêmes périmètre, filtres, recherche et tri que la grille des AMM.
- Concurrence Celery de dev limitée à 2 processus (18 connexions PostgreSQL inutiles auparavant).

### Corrigé
- Stockage S3 des scans : `django-storages[s3]` (boto3) installé, un seul jeu de variables
  `DOCUMENT_STORAGE` + `S3_*` reconnu en dev comme en prod.
- Image frontend nginx : `VITE_API_BASE` vide par défaut (la valeur `/api` produisait des appels `/api/api/v1`).
- Dockerfile backend : le stage par défaut est l'image d'exécution, pas l'image de dev.

## [1.0.0] — 2026-09-05

Première version de production : remplacement du classeur `Dashboard AMM Afrique`.

### Fonctionnel
- Authentification JWT, trois rôles (`CEO_ADMIN`, `HQ_REGULATORY`, `COUNTRY_REGULATORY`), périmètre par pays.
- Référentiels pays, gammes, produits (alias Excel, fusion de doublons).
- AMM : création, édition en ligne, calcul du statut et de l'urgence, historique complet, export Excel/CSV.
- Workflow de renouvellement PLANIFIE → EN_PREPARATION → DEPOSE → EN_INSTRUCTION → OBTENU | REJETE | ABANDONNE.
- Moteur d'alertes paramétrable (J-365, J-180, J-90, J-30, J0, dossier incomplet, décision en retard), escalade siège puis CEO, résolution automatique.
- Notifications in-app temps réel (WebSocket, repli polling), emails, digest hebdomadaire.
- Tableaux de bord Afrique, pays et produit ; cinq dashboards Grafana provisionnés.
- Import idempotent du classeur Excel avec rapport d'anomalies.
- Gestion documentaire : scans PDF versionnés, chronologie inverse, visionneuse, archive ZIP, bibliothèque.

### Exploitation
- Docker Compose dev et prod (Caddy TLS, sauvegarde quotidienne), images GHCR, CI GitHub Actions, workflow Deploy.
- Commande `evaluate_alerts --quiet` et réglage `ALERTS_DISPATCH_MAX_AGE_DAYS` pour une mise en service sans déluge d'emails.
