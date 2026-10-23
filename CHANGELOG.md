# Changelog

Toutes les évolutions notables du projet sont consignées ici.
Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), versionnement [SemVer](https://semver.org/lang/fr/).

## [Non publié]

## [1.0.8] — 2026-10-23

### Ajouté
- **Nouveau calendrier** pour toutes les dates : on choisit l'année, puis le mois, puis le jour (ou on
  tape JJ/MM/AAAA), en français. Sous les dates d'une période, la validité se calcule toute seule
  (« Validité : 5 ans, jusqu'au 06/04/2021 ») et une durée différente de celle du pays est signalée.

### Corrigé
- **Une date de début corrigée refait le calcul sur 5 ans** (durée de validité du pays) : classeurs,
  fiche AMM, renouvellements, création d'AMM et de page. Avant, une fin importée du Dashboard restait
  figée et la correction « ne changeait rien ». Une fin égale à début + durée reste calculée.
- Classeurs : la décision relevée sur le papier conclut le dépôt en cours au lieu de créer un second
  renouvellement (le tampon « DÉPOSÉ » restait) ; une décision plus ancienne que le dépôt prend sa
  place dans l'ordre des dates.
- Classeurs : un renouvellement rejeté ou abandonné ne compte plus de faux manques ; une
  interruption de validité après un renouvellement non daté est détectée ; une page dont la
  décision en vigueur n'est pas scannée le dit (et passe « À scanner ») au lieu de montrer le scan
  d'une autre période comme le sien.
- Alertes :
  - l'alerte DOSSIER se ferme quand le scan arrive ; un dépôt ne ferme plus DOSSIER ni J0 ;
  - une échéance corrigée remplace ses alertes au lieu de les dédoubler ;
  - une alerte DECISION n'est plus classée « Renouvellement obtenu » après un rejet ou un abandon ;
  - J-180 et J-90 tombent le jour du dépôt idéal et de la limite agence affichés ;
  - le motif de résolution s'affiche en clair.
- Durée restante : mois entiers, en années et mois (« 872 j (2 ans et 4 mois) » et non « 29 mois »).
- Tableau de bord : « expire sous 6 mois / 12 mois » compte comme le statut « À renouveler » en fin
  de mois.
- Export Excel : les colonnes RENOUV. donnent la décision en vigueur (et non un renouvellement
  planifié, rejeté ou abandonné, vide).
- Rappel quotidien : le n° cité est celui de la décision qui expire.
- Le lien « Classeur … · page » de la fiche AMM : étiquette du constat à la bonne taille.

## [1.0.7] — 2026-10-22

### Ajouté
- **Corriger un renouvellement** (onglet Renouvellements, crayon) : n° d'AMM, dates de dépôt, de
  décision, de début et de fin (calculée automatiquement ou saisie). Les renouvellements sont
  renumérotés par date et l'échéance, le statut et l'état du dossier de l'AMM sont recalculés ;
  l'ancienne valeur reste dans l'historique.
- **Corriger le classement d'un scan** (onglet Documents, crayon) : période (AMM d'origine ou
  renouvellement), type, date et titre, sans retéléverser le fichier.

### Modifié
- Le siège (Réglementaire siège) peut retirer un scan, comme le CEO : il est archivé et reste dans
  l'historique.
- Une décision ancienne saisie après coup reprend sa place dans l'ordre des dates.

### Corrigé
- Les classeurs et la fiche AMM ne se rafraîchissaient pas après une modification de l'AMM, d'un
  renouvellement ou d'un scan.

## [1.0.6] — 2026-10-20

### Ajouté
- **Menu latéral réductible** : le bouton en bas du menu (‹ / ›) le réduit aux icônes pour laisser la
  place au contenu (classeurs, tableaux) ; le nom de chaque entrée s'affiche en info-bulle. Le choix est
  retenu dans le navigateur.

### Sécurité
- Interface : `follow-redirects` 1.16.1 (dépendance d'axios), failles GHSA-q3jh-wrc6-jgq8 et
  GHSA-8r9p-f939-6h3c publiées le 20/10 et signalées par `npm audit` en CI.

## [1.0.5] — 2026-10-20

### Ajouté
- **Classeurs : pile des décisions et chronologie de l'AMM** (`docs/classeurs-archivage.md`). Toutes
  les décisions scannées, de l'origine au dernier renouvellement, sont agrafées en pile sur la page,
  la plus récente au-dessus. Un clic ouvre la chronologie, de la dernière décision à l'AMM d'origine :
  pièces de chaque période et manques (décision non scannée, date ou n° inconnus, interruption de
  validité, récépissé absent), avec le moyen de les régler (importer le scan depuis la fenêtre).

## [1.0.4] — 2026-10-19

### Corrigé
- **Import des scans classés** : une date plus exacte du classement (décision du 06/04 au lieu du
  16/04 dans le Dashboard) s'applique désormais, même si elle avance un peu l'échéance. Seul un
  recul de plus de six mois (une autre décision, par exemple l'AMM de 2009 au lieu du
  renouvellement de 2019) attend une vérification. Un changement de statut de l'AMM causé par le
  classement est signalé en avertissement. Simulation en production du 19/10 : 589
  avertissements, la plupart des corrections de quelques jours écartées à tort.
- Page d'un import : le placement d'une pièce s'affiche en clair (au lieu de « [object Object] »).

## [1.0.3] — 2026-10-19

### Ajouté
- **Import des scans classés (classement AMM GHPL)** : troisième étape, après le Dashboard et le
  registre. Le manifeste « manifeste_scans_amm_gh.csv » s'importe dans Imports Excel (simulation
  comprise) ; chaque pièce principale est rapprochée de son AMM et de sa période :
  - AMM et produit créés s'ils manquent ; renouvellements obtenus manquants créés ; un dossier
    déposé sans décision est conclu par la décision classée qui le suit ;
  - le classement fait foi pour les dates sûres (date du dossier « RENOUVELLEMENT n - AAAA-MM-JJ »,
    date d'origine « haute » ou « lecture visuelle » de l'année du dossier d'origine) ; une
    correction qui avancerait l'échéance de l'AMM n'est pas appliquée et devient un
    avertissement ; les n° du classement ne font que compléter un n° absent ;
  - récépissés rangés avec le renouvellement qu'ils ont précédé (date de dépôt complétée),
    variations sur la période en vigueur ;
  - renouvellements renumérotés dans l'ordre des dates (une décision ancienne ajoutée après coup
    ne devient pas « la dernière »).
- `scripts/importer_scans_classement.py` (Mac, Python standard) : envoie ensuite chaque fichier à
  sa place, vérifie son SHA-256, reprend là où il s'est arrêté, réessaie quand Render se réveille,
  et écrit un rapport CSV.

### Sécurité
- CI : la faille CVE-2026-106454 de Twisted (serveur IMAP `twisted.mail`, non utilisé par AMM GH)
  est ignorée par `pip-audit` tant qu'aucune version corrigée n'existe.

## [1.0.2] — 2026-10-04

### Corrigé
- **Connexion pendant le démarrage du service** : après une période sans visite, l'API est en
  veille et la première connexion échouait (« Serveur injoignable »). La demande est maintenant
  retentée d'elle-même pendant deux minutes au plus, avec le message « Connexion au service en
  cours ». La page de connexion réveille aussi le service dès son affichage. Si le service ne
  revient pas : « Le service est momentanément indisponible. Veuillez réessayer dans quelques
  instants. » Un refus (identifiants incorrects) n'est pas retenté.

### Sécurité
- CI : audit des dépendances à chaque pull request (`pip-audit` pour Python, `npm audit` pour les
  dépendances livrées de l'interface). Étape 4 du cycle de publication (`docs/versionnement.md`).

## [1.0.1] — 2026-10-04

Première version numérotée selon `docs/versionnement.md`. Elle regroupe tout ce qui a été mis en
ligne depuis la 1.0.0 (47 PR), désormais affiché comme « 1.0.1 » dans l'application.

### En bref
- **Classeurs d'archivage** : jumeau à l'écran de chaque classeur papier, constats Conforme /
  Corriger / Absent, ajout de page, import du scan depuis une page, PDF avec les décisions
  officielles (`docs/classeurs-archivage.md`).
- **Dépôts AMM** : dossier de renouvellement suivi du siège au pays (pièces, échantillons, envoi,
  dépôt, commission, décision), avec messages et ZIP du dossier (`docs/depot-amm.md`).
- **Registre GHPL** : import prudent du classement général des scans, avec avancement visible et
  reprise d'un import coupé (`docs/depot-amm.md`, section 1).
- **Import de dossiers** : rangement automatique, récapitulatif, page compacte avec onglets
  À traiter / En cours / Rangés / Tous et recherche (`docs/workflow-amm.md`, section 8).
- **Version affichée** : le numéro vient de `backend/VERSION` ; l'application n'affiche plus « dev ».

### Import de dossiers : on dépose, c'est rangé (`docs/workflow-amm.md`, section 8)
- **Rangement automatique dès que l'AMM (produit + pays) est identifiée**, sans seuil de
  fiabilité : chaque scan va à sa période (origine ou renouvellement n), les renouvellements
  obtenus lus sont créés, les champs vides complétés, statut / échéance / complétude recalculés,
  bilan et notification. Plus de « Garder / Remplacer », de « Valider » ni de % en avant.
- **Points à vérifier plus tard** (`DossierReviewPoint`) : un écart scan ≠ fiche sur une valeur
  renseignée, un renouvellement en conflit, une décision sans période… ne bloquent plus ; la
  fiche est gardée, le scan rangé, le point listé sur la fiche AMM (badge dans la liste) et sur
  le lot, avec « Appliquer la valeur du scan » (audit `DossierChange`) ou « Ignorer ».
- **Une seule question**, seulement si l'AMM n'est pas identifiable : « c'est quelle AMM ? »
  (sélecteur limité au pays et au périmètre, `POST /dossier-imports/{id}/choose-amm`). Création
  d'AMM uniquement par le siège, sur confirmation.
- **« Voir le scan »** : fichier absent du stockage → 410 « Fichier perdu … réimportez ce
  dossier » au lieu d'un 503 ; la copie déjà rangée dans la fiche est montrée si elle existe.

### Workflow des AMM (règles du responsable, `docs/workflow-amm.md`)
- **Trois statuts, plus un pour la donnée manquante** : **Valide** (vert), **À renouveler**
  (orange, dans les six mois précédant la fin, toujours valide), **Expirée** (rouge, dès le
  lendemain de la date de fin) et **Échéance inconnue** (gris, aucune date connue). « En cours
  d'instruction » disparaît des statuts d'AMM : un dépôt en cours n'empêche plus l'expiration ;
  l'avancement d'un renouvellement (Planifié / Déposé / En instruction) reste porté par le
  renouvellement. Un renouvellement ne compte qu'une fois **obtenu**.
- **Deux dates au lieu d'une** : « Dépôt idéal » (fin − 6 mois, objectif interne) et
  « Limite agence » (fin − 3 mois), affichées dans la fiche, les listes, le tableau de bord,
  l'export et les notifications. Le délai de dépôt par pays (`filing_lead_months`) disparaît.
- **Rappel quotidien** de chaque AMM « À renouveler » aux réglementaires du siège et du pays :
  notification dans l'application et e-mail (`RENEWAL_REMINDER_CHANNELS`), au plus un par AMM,
  destinataire et jour ; il s'arrête dès qu'un renouvellement obtenu repousse l'échéance ou que
  l'AMM expire. Les règles d'alerte existantes (J-365 … DOSSIER, DECISION) sont conservées.
- **Fiche AMM** : frise « Origine → renouvellements obtenus » avec le **document actuel** mis en
  évidence, état du dossier affiché séparément du statut (complet dès que le scan de la décision
  actuelle est rattaché, quelle que soit la validité).
- Migration : toutes les AMM sont recalculées ; les vues `analytics` suivent (`to_renew`,
  `ideal_filing_date`, `agency_filing_deadline`).

### Surveillance
- **Sentry**, actif seulement si `SENTRY_DSN` (web, worker) ou `VITE_SENTRY_DSN` (interface) est
  défini : erreurs et journaux ERROR remontés avec le `request_id` des journaux JSON, la version
  déployée et l'environnement. Aucune donnée personnelle (ni IP, ni cookies, ni corps de requête ;
  identifiant interne de l'utilisateur seulement), traces de performance désactivées par défaut.
  Paquet absent ou DSN vide : l'application démarre comme avant.

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
  Statuts recalculés pour le jour du rejeu après chaque remise à zéro, un seul scénario à la
  fois, `--build` sans risque pour l'image d'origine, état de référence créé par
  `scenarios.py --save-baseline`.

### Ajouté
- **Version de l'API visible.** `/api/v1/health` expose `version` (variable `APP_VERSION` ;
  « dev » si elle est absente ou non conforme : lettres, chiffres et `. _ + -`, 64 caractères au
  plus) et la barre du haut affiche « API en ligne · <version> », « API dégradée » en rouge quand
  la base ne répond plus, « API injoignable » quand l'API ne répond pas. Sonde toutes les 60 s,
  délai de 5 s, sans nouvelle tentative. Le contrôle Redis du health est borné à 1,5 s au total,
  résolution DNS comprise, et les sondes simultanées partagent un même contrôle : un Redis arrêté
  ne ralentit plus la réponse de 4 s. Contrat 200/503 des sondes Railway et Docker inchangé.
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
