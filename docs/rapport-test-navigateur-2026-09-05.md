# Rapport de test navigateur — AMM INNOV

*Sessions du 5 septembre 2026 (deux passes), stack Docker de développement locale (`http://localhost:5173`), navigateur intégré. Trois comptes de démonstration testés : `ceo@amm.local` (CEO_ADMIN), `siege@amm.local` (HQ_REGULATORY), `senegal@amm.local` (COUNTRY_REGULATORY, périmètre Mali + Sénégal).*

## 1. Résultat d'ensemble

L'application est fonctionnelle de bout en bout une fois les correctifs ci-dessous appliqués : authentification, tableaux de bord, grille des AMM, fiche AMM (édition, renouvellements, documents, alertes, historique), centre d'alertes, bibliothèque documentaire, import Excel, administration, temps réel et périmètre par rôle. Le temps réel fonctionne (indicateur « Live », mise à jour immédiate de l'en-tête de la fiche après une transition, badge de notifications).

Mais la version telle qu'elle était au début de la session **n'était pas utilisable** : la connexion échouait (404), un rechargement de page bloquait sur un spinner infini, et deux pages plantaient (Alertes, fiche produit). Toutes ces anomalies relèvent d'un même défaut structurel signalé dans l'analyse d'architecture : le contrat entre l'API et le frontend n'est pas outillé, et les mocks MSW (qui font passer les tests) ne reflètent pas la vraie API.

## 2. Anomalies trouvées et corrigées

| # | Gravité | Symptôme observé | Cause | Correctif (fichier) |
|---|---|---|---|---|
| 1 | Bloquant | Connexion impossible, message « 0 : < », 404 | `VITE_API_BASE=/api` dans `.env` et par défaut dans `docker-compose.yml` → appels `/api/api/v1/…` | `.env`, `docker-compose.yml` (`VITE_API_BASE` vide) |
| 2 | Bloquant | Rechargement ou accès direct par URL : spinner infini | `RequireAuth` : la mise à jour d'`access` démontait l'effet avant son `finally`, `restoring` restait `true` | `frontend/src/app/guards.tsx` (`restoring` dérivé du store) |
| 3 | Bloquant | Après un rechargement réussi, le suivant déconnectait | `ROTATE_REFRESH_TOKENS` côté serveur : le nouveau refresh renvoyé par `/auth/refresh` n'était pas conservé | `frontend/src/api/client.ts` (`setSession` avec le nouveau refresh) |
| 4 | Bloquant | Page Alertes : `Cannot read properties of undefined (reading 'country_iso2')` | Frontend attend `amm_summary`/`amm`, l'API renvoie `amm_id`, `country_iso2`, `product_name`, `effective_end_date` à plat | `types.ts`, `AlertsTable.tsx`, `DocumentsLibraryPage.tsx`, `ProductDetailPage.tsx`, mocks alignés |
| 5 | Bloquant | Fiche produit : `Objects are not valid as a React child (id, raw_name)` | `aliases` renvoyé en objets, frontend attend `string[]` (et les envoie à l'enregistrement, ignorés par l'API) | `backend/apps/catalog/serializers.py` (`AliasListField` lecture/écriture) |
| 6 | Majeur | Modifier un simple commentaire d'AMM pose `original_end_date_manual = True` (la date de fin ne suit plus le pays) | Le formulaire renvoie toujours la date ; le serializer la considérait comme saisie manuellement dès qu'elle était présente | `backend/apps/amm/serializers.py` (comparaison à l'instance) |
| 7 | Majeur | Imports Excel : colonne « Fichier » = UUID, compteurs « — », cartes KPI vides | `file_name` vs `filename` ; compteurs lus à la racine de `summary` au lieu de `summary.totals` | `ImportsPage.tsx`, `ImportDetailPage.tsx`, `types.ts`, mocks |
| 8 | Majeur | Cloche : aucun badge (erreur console « Query data cannot be undefined ») et chaque notification en double | `/unread-count` renvoie `{unread}` (lu `.count`) ; la liste incluait le canal EMAIL | `useNotifications.ts` (`.unread`, filtre `channel=IN_APP`), mocks |
| 9 | Mineur | Message d'erreur illisible « 0 : < » sur réponse HTML | `extractErrorMessage` indexait une chaîne | `client.ts` |

Vérifications faites après correction : `tsc -b --noEmit` et `eslint` passent sur le frontend. Vitest n'a pas pu être lancé depuis l'environnement de test (binaire rollup macOS) : lancer `make test-frontend` et `make test-backend` avant de committer.

## 3. Parcours validés

**CEO_ADMIN.** Connexion ; Dashboard Afrique (1 563 AMM, 973 valides, tableau pays, graphique, top 10) ; Dashboard pays Sénégal (répartition gamme × statut, pipeline 24 mois) ; grille AMM (recherche « LOLIP » → 36 résultats, filtres, export, pagination) ; fiche AMM LOLIP 80MG GN : édition du commentaire (« AMM mise à jour »), historique (acteur et diff), création d'un renouvellement, transitions Planifié → En préparation → Déposé (validation « date de dépôt obligatoire » OK), mise à jour temps réel de l'urgence en « En instruction » ; téléversement d'un PDF (rattaché au renouvellement n°1, 510 o, SHA-256), visionneuse pdf.js, bibliothèque Guinée listant le document ; centre d'alertes : acquittement ; administration : utilisateurs, pays (15), gammes (3), règles d'alerte (6), imports (détail : 1 541 créées, 7 mises à jour, 3 erreurs sur GUINEE « DATE DEBUT » = « IN PROCESS ») ; cloche de notifications ; déconnexion.

**HQ_REGULATORY.** Connexion, redirection vers la page demandée avant login, dashboard complet (tous pays), section Administration visible, page Utilisateurs avec bandeau explicatif « vous pouvez créer des réglementaires pays » et action Modifier limitée au compte réglementaire pays.

**COUNTRY_REGULATORY (ML, SN).** Dashboard restreint à 2 pays (430 AMM) ; pas de section Administration ; `/admin/users` → « Accès refusé » ; fiche d'une AMM hors périmètre → 404 ; `/countries/BJ` → « Ce pays est hors de votre périmètre » ; dialogue Nouvelle AMM : liste des pays limitée à Mali/Sénégal ; centre d'alertes limité à ML/SN, sans bouton Assigner ; résolution d'une alerte avec commentaire OK.

## 4. Seconde passe (après « corrige maintenant et refais un test »)

Tous les points restants ont été corrigés puis revérifiés dans le navigateur, backend redémarré (migration `alerts/0003` appliquée) :

| # | Correctif | Vérification |
|---|---|---|
| 10 | **Sélecteur de produit incomplet** (nouveau bug trouvé) : l'API plafonne `page_size` à 500 et le référentiel compte 856 produits ; `fetchAll` ne lisait que la première page, donc les produits de L à Z étaient introuvables dans « Créer une AMM » et la page Produits affichait « 500 » (`useCatalog.ts` suit désormais `next`) | « LOLIP 80 » proposé dans le sélecteur ; AMM LOLIP 80MG créée à Djibouti, fin calculée 15/01/2031, deadline 15/07/2030 |
| 11 | Top 10 des priorités (dashboard Afrique) limité aux urgences actionnables, tri CRITIQUE → DEPOT_URGENT → A_PLANIFIER puis échéance ; liste des urgences du dashboard pays triée de même côté API (`URGENCY_PRIORITY`) | Dashboard Afrique : 10 AMM expirant dans 10–23 jours ; dashboard Côte d'Ivoire : Critique, Dépôt urgent, À planifier, En instruction, puis expirées |
| 12 | Centre d'alertes trié par échéance la plus récente (`ordering = -due_date`) | Première ligne : J-365 du 05/09/2026 (créé par le passage nocturne de Celery beat à 00:15), puis J-180 du 01/09/2026 |
| 13 | Règle `DECISION` (PRD 6.4, 120 jours) ajoutée aux règles par défaut + migration | Page Règles d'alerte : 7 règles dont DECISION / 120 j / Réglementaire pays |
| 14 | Messages d'erreur en français selon le statut HTTP (404, 5xx, serveur injoignable) et **plus de nouvelle tentative sur une erreur 4xx** (`providers.tsx`) | AMM hors périmètre : « Élément introuvable ou hors de votre périmètre. » affiché immédiatement |
| 15 | Dialogue de téléversement : type suggéré « Récépissé de dépôt » quand le document est rattaché à un renouvellement non obtenu, date pré-remplie avec la date de dépôt, libellé du titre corrigé, `renewal_id` de l'API utilisé pour le remplacement | Récépissé téléversé sur VILDAMET (SN) par le compte pays, rattaché au renouvellement n°1 déposé le 01/03/2026 |
| 16 | Alias produits modifiables (serializer `AliasListField`) | Fiche ACARBOSE : DCI et alias supplémentaire enregistrés et affichés |
| 17 | Le commentaire d'AMM ne pose plus `original_end_date_manual` | Historique de l'AMM créée : seule la ligne `notes` change |
| — | `.gitignore` : `Claude outputs/` | — |

Le renouvellement VILDAMET (SN) déposé le 01/03/2026 dépasse les 120 jours : la règle DECISION créera une alerte au prochain passage de `evaluate_alert_rules` (00:15) — à vérifier demain dans le centre d'alertes du compte pays.

## 5. Points restants

- **Doublons produits** issus de l'import (« ACARBOSE GH 100 MG CPR B100 » GENERALE vs « ACARBOSE GH 100MG CPR B/100 » CARDIO) : la fonction « Fusionner dans… » existe ; c'est une décision métier (quelle fiche garder, quelle gamme) à prendre avant une passe de nettoyage, je ne l'ai pas faite.
- **Autorité réglementaire** vide pour les 15 pays : donnée de référence à saisir dans Administration › Pays.
- **Compte CEO : 99+ notifications non lues** dès le seed ; en production, lancer `evaluate_alerts --quiet` après l'import initial comme prévu dans le README.
- **Couverture pays de la fiche produit** : un réglementaire pays voit le statut du produit dans les autres pays (les cases sont marquées `in_scope: false` par l'API mais restent lisibles). Comportement voulu par le PRD (vue produit transversale) ; à confirmer.
- **Tests automatisés** : `make test-frontend` et `make test-backend` n'ont pas pu être lancés depuis l'environnement de test (binaire rollup macOS, Django absent de la VM) ; les mocks MSW ont été alignés, mais lancer `make test` et `make lint` avant de committer.

## 6. Recommandation

Dix des dix-sept anomalies sont des désaccords de forme entre l'API et le client, invisibles pour la CI parce que les tests frontend tournent contre des mocks écrits à la main. Générer le client TypeScript depuis `/api/schema` (openapi-typescript) et faire échouer la CI en cas de dérive fermerait cette classe de bugs définitivement ; c'est le point n° 1 de l'analyse d'architecture et ces deux sessions de test en sont la démonstration concrète.
