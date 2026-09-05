# Revue complète du projet — 5 septembre 2026

Périmètre : code, architecture, sécurité, structures de données, base de données, concurrence,
charge. Stack de développement Docker locale (PostgreSQL 16, Redis 7, Daphne, Celery), base
réelle importée du classeur (1 563 AMM, 856 produits, 15 pays), 3 comptes de démonstration.

Le cahier des charges de la revue mentionnait une marketplace (vendeurs, boutiques, stocks,
panier, paiements). Ce projet est un suivi réglementaire d'AMM : ces scénarios ont été
transposés au domaine réel (réglementaire siège qui crée pays, produits et AMM ; 30 à 100
utilisateurs simultanés qui consultent, déposent des renouvellements, téléversent des scans et
acquittent des alertes ; concurrence sur un même renouvellement, un même fichier, une même AMM).

## 1. Problèmes critiques découverts

### CRITIQUE — Saturation de PostgreSQL dès 30 utilisateurs simultanés

**Problème** : à 30 utilisateurs, 78 requêtes sur 1 000 échouaient en 500 (`FATAL: sorry, too
many clients already`, plafond de 100 connexions).
**Cause** : sous ASGI (Daphne), Django exécute chaque requête dans un nouveau thread ; avec
`conn_max_age=60` chaque thread ouvrait sa propre connexion et la gardait 60 s. Le worker Celery
de dev (concurrence par défaut = 18 CPU) en tenait 18 autres en permanence.
**Risque** : l'application tombe au premier pic d'activité (rentrée des correspondants, passage du
digest, import).
**Correction** : pool de connexions psycopg natif Django 5.1 (`DB_POOL_MAX_SIZE=20`,
`conn_max_age=0`), les requêtes en excès attendent une connexion libre au lieu d'échouer ;
concurrence Celery fixée à 2 partout ; `psycopg[binary,pool]`.
**Résultat** : 0 erreur à 30, 60 et 100 utilisateurs ; 23 connexions PostgreSQL stables (24 à
vide auparavant, plus de 100 sous charge).

### ÉLEVÉ — Throttle de connexion par adresse IP inutilisable en production

**Problème** : 23 connexions sur 30 rejetées (HTTP 429) pendant le test de charge.
**Cause** : `10/min` par `REMOTE_ADDR`. Derrière Render, Caddy ou nginx, toutes les requêtes
portent l'IP du proxy : 10 connexions par minute **pour toute l'entreprise**. Même chose derrière
le NAT d'un bureau.
**Risque** : verrouillage de tous les utilisateurs le matin ; et protection illusoire contre la
force brute distribuée (aucune limite par compte).
**Correction** : `NUM_PROXIES` (1 en prod) pour lire la vraie IP dans `X-Forwarded-For` ;
30/min par IP **et** 10/min par compte visé ; validateurs de mot de passe complétés.
**Résultat** : 30 connexions simultanées acceptées, force brute limitée par compte.

### ÉLEVÉ — Trois courses de concurrence (mesurées avant, fermées après)

| Scénario (10 requêtes simultanées) | Avant | Après |
|---|---|---|
| Création d'un renouvellement sur la même AMM | 3 renouvellements ouverts | 1 (9 × 400) |
| Transition PLANIFIE → EN_PREPARATION | 10 acceptées | 1 (9 × 400) |
| 5 × EN_INSTRUCTION + 5 × ABANDONNE sur un dossier déposé | 10 acceptées, état final aléatoire | transitions sérialisées, chaque étape validée par la machine à états |
| Envoi du même PDF | 10 documents identiques | 1 (9 × 400) |

**Cause** : contrôles « lire puis écrire » sans verrou (existence d'un renouvellement ouvert,
transition autorisée, empreinte SHA-256 déjà présente).
**Correction** : `select_for_update` sur l'AMM à la création d'un renouvellement et sur le
renouvellement pendant une transition (relecture du statut sous verrou) ; contrainte d'unicité
partielle `(amm, sha256) WHERE archived_at IS NULL` (migration `documents/0002`) avec conversion
de l'`IntegrityError` en erreur 400.

### ÉLEVÉ — Contournement de la machine à états des renouvellements

**Problème** : `PATCH /renewals/{id}` acceptait `workflow_status`, donc un passage direct
PLANIFIE → OBTENU sans dépôt ni décision, hors des règles de `workflow.transition`.
**Correction** : le statut est figé après création ; seule `/renewals/{id}/transition` le change.
**Résultat** : 400 explicite ; les autres champs restent modifiables.

## 2. Vulnérabilités de sécurité

| Gravité | Constat | Correction |
|---|---|---|
| MOYEN | Couverture pays d'un produit : un réglementaire pays lisait le statut et la date de fin des AMM des autres pays (`in_scope: false` mais données présentes). | Données masquées hors périmètre, libellé « Hors périmètre » côté frontend. |
| MOYEN | Une alerte pouvait être assignée à un utilisateur sans accès au pays concerné. | Refus 400 si l'assigné n'a pas accès au pays. |
| MOYEN | `/metrics` public : compteurs d'AMM par statut, volumétrie des requêtes. | `METRICS_TOKEN` optionnel (Bearer), utilisé par le scrape Grafana Cloud. |
| MOYEN | Classeurs Excel importés parsés sans protection contre les XML piégés (« billion laughs »). | `defusedxml` installé, utilisé automatiquement par openpyxl. |
| FAIBLE | Validateurs de mot de passe minimaux. | Similarité avec l'email et mots de passe numériques refusés. |
| FAIBLE | Refresh token JWT en `localStorage` (exposé à un XSS). | Conservé : aucun point d'injection HTML trouvé (pas de `dangerouslySetInnerHTML`, React échappe tout), jeton d'accès en mémoire seulement, rotation et liste noire côté serveur. Alternative cookie httpOnly notée en dette. |
| FAIBLE | Jeton d'accès WebSocket dans la query string (`/ws/?token=`). | Daphne ne journalise pas la query string ; un proxy pourrait. Passage par sous-protocole recommandé, non fait (durée de vie 15 min). |
| FAIBLE | `/api/docs` et `/api/schema` publics. | Conservé (aucune donnée, schéma seulement). |

Vérifié sans anomalie : aucun secret dans le bundle frontend (les mocks MSW ne sont pas
emballés en production), aucune injection SQL (ORM, SQL brut limité aux vues analytics et au
rôle Grafana avec échappement), CSRF hors sujet pour l'API JWT et actif sur `/admin`, CORS à
liste explicite en prod, périmètre pays appliqué par `CountryScopedQuerysetMixin` sur AMM,
renouvellements, documents, alertes (tests existants + nouveaux), IDOR impossible sur les fichiers
(404 hors périmètre), validation des envois par octets magiques, taille 25 Mo, SHA-256.

## 3. Code mort supprimé

Backend : `IsCeoAdmin`, `MarketingAuthorization.pending_renewal`,
`DocumentQuerySet.not_archived`, `parsed_row_dict`, `OUTCOME_ORDER`.
Frontend : `ROLE_ORDER`, `hasRole`, `fileUrlFromApi`, `downloadFromApi`.
Aucune dépendance inutilisée : chaque paquet de `requirements.txt` et `package.json` est importé.

## 4. Parties simplifiées

- `ExportView` réimplémentait périmètre, filtres et une recherche différente de la grille
  (sans alias ni numéros de renouvellement) : il réutilise désormais `AmmViewSet` ; l'export
  correspond exactement à la vue filtrée (test ajouté).
- `country_dashboard` calculait le tableau Afrique complet pour en extraire une ligne : agrégat
  direct sur le pays.
- `product_coverage` : une requête par pays pour le périmètre ; un `set` d'identifiants.
- `recipients_for` : une requête par destinataire (`countries.filter().exists()`) ; une seule
  requête avec `Q`.
- `amm_history` : `select_related("history_user")`.

## 5. Problèmes SOLID corrigés et découpages

Le code est déjà découpé par domaine (10 apps Django, 8 dossiers `features` React), aucun fichier
ne dépasse 360 lignes hors mocks, les services métier (`status`, `workflow`, `engine`, `ingest`)
sont isolés des vues. Deux couplages notés et **volontairement conservés** : le modèle AMM
recalcule son état dans `save()` via le service `status` (garantit la cohérence quel que soit le
point d'écriture) ; les routes documents sont des fonctions appelées depuis les viewsets AMM,
pays, produit (l'URL suit la ressource parente). Aucun découpage artificiel n'a été fait.
Responsabilité corrigée : la création d'un renouvellement (verrou + règle « un seul ouvert ») est
sortie du serializer pour rejoindre le service `workflow`.

## 6. Structures de données

Adaptées : dictionnaires pour les jointures en mémoire (couverture, import), `set` pour les
périmètres, `prefetch_related` pour les renouvellements, `Exists` pour le drapeau « scan
présent ». Contraintes d'unicité : produit × pays, AMM × règle × échéance, AMM × séquence,
code × pays, email, alias, et désormais AMM × SHA-256 (actif). Index : statut, urgence, date de
fin, `(pays, statut)`, chronologie des documents. Pagination 50 / 500 max. Cache : inutile au
volume actuel (aucun endpoint au-dessus de 8 requêtes SQL, voir § 8). Aucune structure changée
pour le principe.

## 7. Base de données

Comptage des requêtes SQL par endpoint (base réelle, compte siège) :

| Endpoint | Requêtes SQL | Latence à vide |
|---|---|---|
| `GET /analytics/africa` | 3 | 136 ms (première) puis 2 ms |
| `GET /analytics/country/SN` | 7 | 7 ms |
| `GET /amms?page_size=50` | 4 | 10 ms |
| `GET /amms?page_size=500` | 4 | 33 ms |
| `GET /amms/{id}` | 3 | 3 ms |
| `GET /amms/{id}/history` | 8 | 5 ms |
| `GET /amms/{id}/documents?group=period` | 6 | 4 ms |
| `GET /alerts` (centre) | 3 | 6 ms |
| `GET /products?page_size=500` | 4 | 37 ms |
| `GET /analytics/export?format=csv` | 3 | 79 ms |

Aucune requête N+1. Transactions : une par onglet à l'import, atomiques sur les transitions,
l'ingestion de documents et la fusion de produits. Stock, commandes, paiements : sans objet.

## 8. Problèmes de concurrence

Voir § 1. Restent tolérés : deux `PATCH` simultanés sur une même AMM (dernier écrit gagne, tracé
dans l'historique) ; double création d'AMM sur le même produit × pays (contrainte d'unicité
→ 500 au lieu de 400, cas rarissime). Le moteur d'alertes est idempotent (`get_or_create` sous
contrainte unique) et le worker Celery tourne en une instance avec beat intégré.

## 9. Résultats du test à 30 utilisateurs (après correctifs)

30 utilisateurs simultanés, 3 rôles, 2 itérations chacun d'un parcours de 16 requêtes
(dashboards, grille, recherche, 3 fiches, documents, historique, alertes, notifications,
référentiel produits, modification d'une note, acquittement d'une alerte, export CSV) :
1 003 requêtes en 12,5 s, 80 req/s, 0 erreur.

| Endpoint | p50 | p95 |
|---|---|---|
| `GET /products` (500 lignes) | 583 ms | 765 ms |
| `PATCH /amms/{id}` | 501 ms | 748 ms |
| `POST /alerts/{id}/acknowledge` | 404 ms | 765 ms |
| `GET /analytics/export` (CSV) | 350 ms | 538 ms |
| `GET /amms` (liste) | 257 ms | 281 ms |
| `GET /amms/{id}/history` | 242 ms | 305 ms |
| `GET /analytics/africa` | 177 ms | 412 ms |
| `GET /amms/{id}` | 157 ms | 277 ms |
| `GET /alerts` (centre) | 148 ms | 212 ms |

Ressources au pic : backend 110 % CPU (un processus), PostgreSQL 38 %, 23 connexions.

## 10. Points de rupture identifiés

| Utilisateurs | Requêtes | Débit | p50 fiche AMM | p50 PATCH | Erreurs |
|---|---|---|---|---|---|
| 30 | 1 003 | 80 req/s | 157 ms | 501 ms | 0 |
| 60 | 2 003 | 81 req/s | 369 ms | 1 160 ms | 0 |
| 100 | 3 337 | 81 req/s | 672 ms | 1 931 ms | 0 |

- **Ce qui casse en premier** : plus rien ne casse jusqu'à 100 utilisateurs ; la latence croît
  linéairement (file d'attente) car le débit plafonne à 80 req/s.
- **Goulot** : le processus Python unique de Daphne, borné par le GIL à ~1,1 cœur ; PostgreSQL
  reste à 25 %, Redis négligeable, mémoire backend 235 Mo.
- **Avant correctif**, le point de rupture était PostgreSQL à 30 utilisateurs (voir § 1).
- **Endpoints les plus coûteux** : `PATCH /amms` (recalcul d'état, historique, réconciliation des
  alertes, trois publications Redis), `GET /products` en 2 pages de 500 (856 produits sérialisés
  avec alias), export CSV, acquittement (historique + publication).
- **Sur Render starter (0,5 CPU)** : compter ~35 à 40 req/s, soit 30 utilisateurs actifs avec des
  temps de réponse sous la seconde. Un usage réglementaire réel (quelques requêtes par minute et
  par personne) laisse une marge confortable.

## 11. Limites actuelles

Un seul processus web ; throttles en cache mémoire locale (par processus) ; export construit en
mémoire (acceptable à 1 500 lignes, à surveiller au-delà de 20 000) ; pas de miniatures ni de
conversion image → PDF (`img2pdf` absent, les JPEG/PNG sont stockés tels quels) ; import sans
prévisualisation ; tests frontend sur mocks écrits à la main (dérive de contrat possible, cf.
rapport de test navigateur).

## 12. Optimisations réalisées

Pool de connexions ; concurrence Celery ; requêtes N+1 (historique, destinataires, couverture) ;
agrégat pays direct ; export unifié.

## 13. Optimisations recommandées, non nécessaires immédiatement

1. Plusieurs processus web (Daphne × 2 à 4 derrière nginx, ou `uvicorn --workers`) quand la
   fréquentation dépassera 30 utilisateurs actifs en continu : débit ×2 à ×4, le pool par
   processus doit alors être réduit (`DB_POOL_MAX_SIZE` × processus ≤ 80 sur Render basic).
2. Cache Redis 60 s sur `/analytics/africa` et `/products` (invalidé par les événements temps réel
   déjà émis) si les dashboards deviennent l'écran d'accueil de tous.
3. Générer le client TypeScript depuis `/api/schema` (openapi-typescript) et faire échouer la CI en
   cas de dérive : la cause des dix anomalies du test navigateur.
4. Sélecteur de produits en recherche serveur (`?search=`) plutôt qu'un chargement des 856
   produits en deux pages.

## 14. Dette technique restante

Refresh token en `localStorage` (cookie httpOnly possible mais impose CSRF) ; jeton WebSocket en
query string ; PRD « session 12 h » contre refresh 7 jours glissant ; `img2pdf` pour les photos
de smartphone ; `mocks/handlers.ts` de 1 000 lignes ; dashboard Grafana « Technique » dépendant
d'un Prometheus ; doublons produits issus de l'import (décision métier).

## 15. Évaluation globale

| Axe | Note | Commentaire |
|---|---|---|
| Architecture | B+ | Monolithe modulaire lisible, services métier isolés, temps réel sobre (identifiants seulement). Pas de sur-ingénierie. |
| Qualité du code | B+ | Fichiers courts, typage, tests (130 backend, 31 frontend), lint strict. Contrat API/front à outiller. |
| Sécurité | B | Bonne base (JWT rotatif, périmètre pays systématique, validation des envois). Corrigés aujourd'hui : fuite de couverture, assignation, throttle, machine à états. |
| Performances | B | 80 req/s par processus, aucun N+1, requêtes de 2 à 8 par écran. |
| Scalabilité | C+ | Verticale seulement ; multi-processus non configuré ; suffisant pour l'usage cible (15 pays, quelques dizaines d'utilisateurs). |
| Maintenabilité | A- | Conventions homogènes, migrations propres, documentation à jour, CI. |
| Robustesse en production | B | Après correctifs : pool, verrous, contrainte d'unicité, 0 erreur à 100 utilisateurs. Un seul processus reste un point de fragilité. |

## 16. Suite donnée le même jour

Après ce rapport : contrat API ↔ frontend outillé (schéma OpenAPI et types générés versionnés,
vérification en CI, assertions de compatibilité dans `frontend/src/api/contract.ts`) qui a révélé
et corrigé quatre dérives supplémentaires (`last_renewal`, `amm_id` des renouvellements,
`sent_at`, `range`) ; recherche serveur des produits dans le dialogue de création d'AMM ; jeton
WebSocket transmis par sous-protocole ; session de 12 heures glissantes conforme au PRD.

Vérification finale : ruff, 130 tests backend (SQLite et PostgreSQL), eslint, prettier, tsc,
31 tests frontend, migrations cohérentes, script de concurrence rejoué au vert.
