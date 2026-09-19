# Changelog

Toutes les évolutions notables du projet sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement [SemVer](https://semver.org/lang/fr/).

## [Non publié]

### Résilience (campagne de chaos du 18/09/2026, `docs/audit-resilience/RAPPORT.md`)
- **Redis devient optionnel.** Le temps réel part après le commit, borné à 1 s, derrière un
  disjoncteur ; sans Redis on se connecte toujours (repli local du throttle) et les écritures ne
  l'attendent plus. Mesuré : Redis figé sous 40 utilisateurs faisait échouer les lectures et durer
  les écritures 25 s.
- **Délais bornés** sur PostgreSQL (`connect_timeout`, `statement_timeout`, `lock_timeout`,
  `idle_in_transaction_session_timeout`), Redis, S3 et Gmail, réglables par variables
  d'environnement (`.env.example`). Erreur de base ou pool saturé : 503 JSON avec `Retry-After`.
- **Aucune tâche perdue.** Acquittement tardif des tâches Celery ; `recover_pending_work` (toutes
  les 5 min) republie e-mails non partis, aperçus manquants, analyses en attente, et libère les
  analyses interrompues ; e-mails relancés sur ~15 min puis jusqu'à ~5 h, tentatives et dernière
  erreur tracées (`send_attempts`, `last_error`), `Message-ID` stable.
- **Écritures protégées.** `PATCH` d'AMM et de renouvellement atomiques et verrouillés (plus de
  mise à jour perdue ni de modification sans historique) ; une seule version courante par scan ;
  la même décision envoyée deux fois n'en crée qu'une (`200` au second envoi).
- **Exploitation.** uvicorn aussi en un seul processus (arrêt gracieux, `GRACEFUL_TIMEOUT`) ;
  `/api/v1/health/live` ; journaux JSON avec `X-Request-ID` propagé aux tâches ; compteurs
  `amm_degraded_operations_total` ; vue `analytics.v_ops_backlog` pour les alertes Grafana ;
  `manage.py check_integrity` (12 invariants), lancé chaque nuit.
- nginx résout `backend` et `grafana` dynamiquement : il démarre sans Grafana et suit une
  nouvelle IP du backend. Archive ZIP envoyée en flux, bloc par bloc, y compris sous ASGI, et scans lus depuis S3
  sans téléchargement parallèle en mémoire. Reconnexion
  WebSocket avec jitter ; un événement d'AMM ne part plus qu'au groupe de son pays.
- Laboratoire de chaos rejouable : `chaos/` (Compose jetable, toxiproxy, scénarios avant/après).

### Ajouté
- **Le frontend est publié par la CI** (job `netlify`), sur un push vers `main` et seulement
  après le vert du backend et du frontend. Il publie l'état commité : `netlify deploy --build`
  lancé depuis un poste construit le dossier de travail et peut mettre en ligne des
  modifications non commitées — c'est arrivé le 10 septembre. `make deploy-frontend` reste
  disponible en dépannage mais refuse un dépôt non propre. Secrets requis :
  `NETLIFY_AUTH_TOKEN` et `NETLIFY_SITE_ID` ; à défaut le job avertit et passe son tour.
- CI : `makemigrations --check --dry-run` échoue si un modèle a changé sans migration, ou si une
  migration écrite à la main ne correspond pas à l'état des modèles.
- **Retour en arrière sur un renouvellement.** Le plus récent s'annule d'un geste (`DELETE
  /api/v1/renewals/{id}`, bouton sur sa carte) : l'AMM est aussitôt recalculée d'après le
  renouvellement précédent ou son AMM d'origine — elle peut redevenir expirée. Les scans
  rattachés à la décision annulée sont archivés, jamais reportés sur l'AMM d'origine. Seul le
  dernier est annulable : revenir en arrière n'est pas trouer l'historique, que `simple-history`
  conserve avec le détail de ce qui a disparu.

### Modifié
- Création d'AMM : quand la recherche de produit ne donne rien, un réglementaire pays lit
  désormais que le catalogue est tenu par le siège, au lieu de rester devant une liste vide. Les
  permissions sont inchangées — les pays créent AMM, renouvellements et documents dans leur
  périmètre, le catalogue et l'administration restent au siège.
- **Ajouter un renouvellement se fait en une étape.** Un numéro et une date de début suffisent :
  le statut se déduit de la saisie (une date, c'est une décision en main), l'échéance vient de la
  durée de validité du pays et l'AMM est recalculée — une AMM expirée redevient valide d'elle-même.
  Les réglementaires pays comme le siège y ont accès, chacun dans son périmètre. Si un
  renouvellement est déjà ouvert, la décision le conclut au lieu d'être refusée : même dossier,
  même n° d'ordre, date de dépôt conservée. Le workflow (Planifié → Déposé → En instruction)
  reste disponible pour suivre un dépôt en cours, en action secondaire.
- **L'état du dossier n'est plus déclaré, il est constaté.** Il vaut « complet » quand la décision
  qui fait foi — le dernier renouvellement obtenu, sinon l'AMM d'origine — porte son scan, et
  « incomplet » sinon. Le champ devient donc calculé : lecture seule dans l'API et dans l'admin,
  recalculé à chaque ajout, remplacement ou archivage de scan. « Inconnu » disparaît, et la
  colonne « dossier » du classeur Excel n'est plus appliquée à l'import.

### Mise en production (7 septembre 2026)
- Frontend sur Netlify (https://amm-innov.netlify.app), API, worker, PostgreSQL et Redis sur
  Railway ; scans PDF et classeurs d'import sur un bucket Railway (S3, région `ams`,
  `S3_ADDRESSING_STYLE=virtual`).
- Données : 15 pays, 3 gammes, 601 produits, 1 548 AMM, 500 renouvellements, importés du classeur
  (3 lignes en erreur, 104 avertissements, aucun écart de statut avec l'Excel) ; 833 alertes
  historiques créées sans notification (`evaluate_alerts --quiet`).
- La clé de rapprochement des produits a fait son effet : zéro doublon à l'import, contre
  185 groupes sur l'import local antérieur au correctif.

### Ajouté
- Déploiement Netlify + Railway : `netlify.toml`, `railway.json`, guide `docs/deploiement-netlify-railway.md`.
- Revue complète du 5 septembre 2026 (`docs/rapport-revue-2026-09-05.md`) : tests de charge à 30, 60 et
  100 utilisateurs, tests de concurrence, durcissement (voir « Corrigé » et « Sécurité »).
- Pool de connexions PostgreSQL (psycopg, `DB_POOL_MAX_SIZE`) : sans lui, l'API saturait PostgreSQL
  (« too many clients ») dès 30 utilisateurs simultanés sous ASGI.
- `/metrics` protégé par `METRICS_TOKEN` (optionnel) ; `NUM_PROXIES` pour lire la vraie IP cliente.

- Contrat API ↔ frontend outillé : `backend/schema.yaml` (OpenAPI) et `frontend/src/api/schema.d.ts`
  générés et vérifiés en CI (`make api-check`) ; `src/api/contract.ts` fait échouer `tsc` dès qu'une
  réponse de l'API n'est plus assignable aux types du frontend. Quatre dérives corrigées au passage :
  `last_renewal` (colonnes et fiche AMM vides), `amm_id` des renouvellements (redirection
  `/renewals/{id}` cassée), `sent_at` nullable, `range` produit nullable.
- Sélecteur de produit du dialogue « Nouvelle AMM » en recherche serveur (20 résultats) au lieu du
  chargement des 856 produits.
- Jeton WebSocket transmis dans le sous-protocole `amm.jwt` au lieu de l'URL.
- Session de 12 heures glissantes (PRD US1.1) : `REFRESH_TOKEN_LIFETIME` passe de 7 jours à 12 h.
- Plusieurs processus web : `WEB_CONCURRENCY` (1 = Daphne, N = uvicorn avec N workers). Mesuré :
  3 workers font passer le débit de 80 à 167 req/s, 0 erreur à 100 utilisateurs, latence divisée par 2 à 3.
- Cache Django sur Redis : throttles de connexion partagés entre les processus web.
- Photos JPEG/PNG converties sans perte en PDF à l'envoi (`img2pdf`) ; image illisible refusée.
- `/api/docs` et `/api/schema` réservés aux utilisateurs connectés (session admin ou JWT).
- Double création simultanée d'une AMM (même produit × pays) : 400 explicite au lieu de 500.
- Import à blanc (PRD US7.1) : case « Simulation » à l'envoi du classeur, `import_excel --dry-run` ;
  rapport complet (lignes, compteurs, anomalies) sans aucune écriture.
- Doublons de produits : clé de rapprochement `Product.key` (lettres et chiffres), l'import
  retrouve un produit connu malgré une ponctuation différente ; `GET /products/duplicates`,
  `POST /products/merge-duplicates` (CEO, fusionne les groupes sans AMM dans un même pays),
  commande `product_duplicates [--merge]`, écran « Doublons probables » dans la liste des produits.
- Fusion de produits depuis la fiche produit : le frontend envoyait `target_id` là où l'API attend
  `duplicate_id` (bouton inopérant) ; contrat étendu aux corps de requête.

- Répétition du premier déploiement (settings de production, base vide, S3 MinIO, 2 workers
  uvicorn, worker Celery) : quatre blocages corrigés. Le WebSocket refusait l'origine du frontend
  quand il n'est pas servi par l'API (Netlify face à Railway) : les origines CORS sont désormais
  acceptées ; le worker Celery pouvait démarrer avant les migrations du service web (il les
  attend) ; `.dockerignore` (le contexte de build envoyait 550 Mo de `node_modules`) ; sommes de
  contrôle boto3 désactivées sauf exigence (compatibilité Cloudflare R2) et adressage `path`.
  configuration Railway : un seul processus web sur le plan starter (512 Mo), cookie de session
  `SameSite=None` tant que Netlify et l'API restent sur deux domaines.

### Ajouté
- Envoi des e-mails par l'**API Gmail** en HTTPS (`EMAIL_URL=gmail://`, OAuth2 `gmail.send`,
  `scripts/gmail_oauth.py` pour le jeton) : Railway bloque tous les ports SMTP sortants, mesuré
  depuis un conteneur (25, 465, 587, 2525 injoignables ; 443 ouvert).

### Corrigé
- `EMAIL_URL` : le schéma `smtp+tls://`, documenté partout, n'activait pas STARTTLS (le chiffrement
  ne s'obtenait qu'avec `?tls=1`) ; toute configuration SMTP sur le port 587, Gmail compris, aurait
  échoué. Le schéma pilote désormais le chiffrement, le port par défaut suit (587 ou 465), et un
  délai maximal de 15 s évite qu'un serveur muet ne bloque le worker.

### Sécurité
- Dépendances : Django 5.1 (fin de support sécurité) remplacé par Django 5.2 LTS (5.2.17, corrige
  7 CVE 2026), Django REST framework 3.17.2 (2 CVE), pip de l'image mis à jour ; `pip-audit` et
  `npm audit` à zéro.
- Refresh token retiré du `localStorage` : cookie `httpOnly` limité à `/api/v1/auth`, SameSite=Lax,
  rotation à chaque rafraîchissement, contrôle de l'en-tête `Origin` sur refresh et logout.
  Un domaine commun frontend/API est requis en production (guide de déploiement, § 1 bis).
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
