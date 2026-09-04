# PRD — AMM INNOV
## Plateforme de suivi des Autorisations de Mise sur le Marché (AMM) en Afrique

| Champ | Valeur |
|---|---|
| Version | 1.0 |
| Date | 04/09/2026 |
| Source de référence | `Dashboard AMM Afrique 18_08_2026 version 2.1.xlsx` |
| Études | [Faisabilité fonctionnelle](docs/faisabilite-fonctionnelle.md) · [Faisabilité non fonctionnelle](docs/faisabilite-non-fonctionnelle.md) · [Conception UML](docs/conception.md) |
| Stack cible | React + TypeScript, Django + Django REST Framework, PostgreSQL, Grafana |
| Statut | Brouillon pour validation |

---

## 1. Contexte et problème

Le suivi des AMM est aujourd'hui réalisé dans un classeur Excel composé d'un onglet `DASHBOARD` et d'un onglet par pays. L'analyse du classeur donne la photographie suivante au 18/08/2026 :

| Indicateur | Valeur |
|---|---|
| Pays suivis | 15 |
| AMM suivies | 1 548 |
| AMM valides | 963 (62 %) |
| AMM expirées | 501 |
| AMM en cours d'instruction (« IN PROCESS ») | 71 |
| AMM au statut indéterminé (date illisible ou absente) | 13 |
| AMM expirant dans les 6 mois | 121 |
| AMM expirant dans les 12 mois | 166 |
| Dossiers complets | 77 % |

Pays couverts : Bénin, Burkina Faso, Cameroun, Côte d'Ivoire, Congo, Djibouti, Gabon, Gambie, Guinée, Madagascar, Mali, Niger, Sénégal, Tchad, Togo.

Gammes de produits : Générale, Cardio, Bien-être.

### 1.1 Limites du classeur actuel

1. **Aucune alerte proactive.** Les échéances ne sont visibles qu'en ouvrant le fichier. Une AMM qui expire sans renouvellement déposé entraîne une rupture de commercialisation dans le pays.
2. **Formules fragiles.** Le statut, la date de fin (date de début + 5 ans) et les compteurs du dashboard reposent sur des formules `SUMPRODUCT`/`IF` de plusieurs centaines de caractères, dupliquées par onglet. Toute insertion de colonne casse le calcul.
3. **Saisie non contrôlée.** Dates saisies en texte (« DATE ILLISIBLE — A RESSAISIR »), numéros d'AMM stockés en nombre flottant (Cameroun : `2021179002.0`), libellés de gamme non homogènes (`GAMME GENERAL`, `GAME CARDIO`), 856 libellés produits distincts pour environ 300 produits réels.
4. **Onglets en double.** Anciens formats (« 3 blocs par gamme ») conservés à côté du format normalisé pour Bénin, Guinée, Togo et Côte d'Ivoire.
5. **Pas d'historique.** Un seul « dernier renouvellement » est conservé ; les renouvellements précédents sont écrasés. Aucune trace de qui a modifié quoi.
6. **Travail collaboratif impossible.** Un seul fichier, pas de droits par pays, pas de temps réel.
7. **Pas de suivi du processus de renouvellement.** On sait qu'un dossier est « complet » ou « incomplet », mais pas s'il est préparé, déposé, en instruction, ni quand.

### 1.2 Vision

Une application web unique, multi-utilisateurs, qui devient la source de vérité des AMM : elle calcule les statuts, déclenche les alertes de dépôt **6 mois avant expiration**, suit le cycle de renouvellement, et expose des tableaux de bord en temps réel pour la direction et les équipes réglementaires.

---

## 2. Objectifs et indicateurs de succès

| Objectif | Indicateur | Cible à 12 mois |
|---|---|---|
| Zéro expiration non anticipée | AMM arrivées à expiration sans dossier déposé | 0 |
| Anticipation du dépôt | % des renouvellements déposés ≥ 6 mois avant expiration | ≥ 90 % |
| Fiabilité des données | AMM au statut « Indéterminé » | < 1 % |
| Complétude des dossiers | % « Dossier complet » | ≥ 95 % |
| Adoption | Utilisateurs actifs hebdomadaires / utilisateurs créés | ≥ 80 % |
| Abandon d'Excel | Le classeur n'est plus mis à jour | 3 mois après mise en production |

---

## 3. Utilisateurs

| Persona | Rôle applicatif | Besoins clés |
|---|---|---|
| **Réglementaire pays** | `COUNTRY_REGULATORY` | Dépose les AMM et les renouvellements auprès de l'autorité de son pays et en assure le suivi : saisie des numéros et dates, upload des scans, réponse aux alertes, état du dossier. Périmètre limité à ses pays. |
| **Réglementaire siège** | `HQ_REGULATORY` | Coordonne les activités réglementaires de tous les pays ; crée et gère les comptes des réglementaires pays et leurs affectations ; priorise et assigne ; paramètre les règles d'alerte ; lance les imports et contrôle la qualité des données. |
| **CEO** | `CEO_ADMIN` | Administrateur de l'application. Vue d'ensemble : couverture réglementaire par pays et par gamme, risques de rupture, activité des équipes, Grafana. Gère les comptes siège ; seul habilité à supprimer un document. |

Héritage des droits : le CEO possède tous les droits du siège, qui possède tous les droits d'un réglementaire pays étendus à tous les pays. Les rôles sont détaillés dans [docs/conception.md](docs/conception.md).

---

## 4. Glossaire

| Terme | Définition |
|---|---|
| **AMM** | Autorisation de Mise sur le Marché délivrée par l'autorité réglementaire d'un pays pour un produit donné. |
| **AMM d'origine** | Première autorisation obtenue (date de début, numéro, date de fin). |
| **Renouvellement** | Nouvelle autorisation prolongeant l'AMM. Peut porter un nouveau numéro. |
| **Durée de validité** | 5 ans par défaut (règle du classeur : date de fin = date de début + 5 ans). Paramétrable par pays. |
| **Date de fin effective** | Date de fin du dernier renouvellement obtenu, sinon date de fin de l'AMM d'origine. |
| **Deadline de dépôt** | Date de fin effective − délai de dépôt (6 mois par défaut, paramétrable par pays). |
| **Statut AMM** | Valeur calculée : `VALIDE`, `EXPIRE`, `IN_PROCESS`, `INDETERMINE`. |
| **État du dossier** | Complétude documentaire : `COMPLET` ou `INCOMPLET`. |
| **Gamme** | Famille commerciale : Générale, Cardio, Bien-être. |
| **Document AMM** | Fichier PDF scanné de l'autorisation délivrée par l'autorité (ou du récépissé de dépôt, du courrier de décision). Daté de la date figurant sur le document. |
| **Dossier documentaire** | Ensemble des documents d'une AMM, présenté en chronologie inverse : le document le plus récent en premier, le plus ancien en dernier. |

---

## 5. Périmètre

### 5.1 Inclus (MVP)
- Référentiels : pays, gammes, produits, utilisateurs et rôles.
- Gestion des AMM : création, modification, historique complet des renouvellements.
- Calcul automatique du statut et des dates de fin, fidèle aux règles du classeur.
- Workflow de renouvellement (planifié → préparé → déposé → en instruction → obtenu/rejeté).
- Moteur d'alertes paramétrable, avec la règle par défaut **J−180 jours = deadline de dépôt**.
- Notifications in-app en temps réel et par email ; digest hebdomadaire.
- Tableau de bord applicatif reprenant l'onglet `DASHBOARD` en temps réel.
- Import initial du classeur Excel avec rapport d'anomalies ; export Excel/CSV.
- Gestion documentaire : stockage des AMM scannées en PDF (origine et chaque renouvellement), récépissés et courriers ; classement chronologique du plus récent au plus ancien ; visionneuse PDF intégrée ; téléchargement unitaire ou groupé.
- Journal d'audit de toutes les modifications.
- Tableaux de bord Grafana (métier et technique).

### 5.2 Exclu (MVP)
- Soumission électronique aux autorités (eCTD).
- Gestion des variations d'AMM (changements de formule, de site, etc.) — prévue V2.
- Notifications SMS/WhatsApp — prévues V2 (architecture prête).
- OCR des scans et extraction automatique du numéro et des dates d'AMM — prévus V2 (les métadonnées sont saisies manuellement au MVP).
- Application mobile native — le web sera responsive.
- Gestion des prix et remboursements.

---

## 6. Règles métier

### 6.1 Calcul de la date de fin
`date_fin = date_debut + durée_validité_pays` (5 ans par défaut). Modifiable manuellement si l'autorité a délivré une durée différente ; la valeur manuelle prime et est tracée.

### 6.2 Calcul du statut (transcription de la formule Excel)
```
si aucune AMM d'origine et aucun renouvellement           → INDETERMINE
si le dernier renouvellement a une date de fin valide     → VALIDE si date_fin ≥ aujourd'hui, sinon EXPIRE
sinon si un renouvellement est marqué « déposé/en cours » → IN_PROCESS
sinon si la date de fin d'origine est absente/illisible   → INDETERMINE
sinon                                                     → VALIDE si date_fin_origine ≥ aujourd'hui, sinon EXPIRE
```
Le statut est recalculé à chaque modification et par un traitement quotidien à 00:05 (heure Dakar), car il dépend de la date du jour.

### 6.3 Niveaux d'urgence (dérivés du statut et de la date de fin effective)

| Niveau | Condition | Couleur |
|---|---|---|
| `OK` | fin > 12 mois | vert |
| `A_PLANIFIER` | 6 mois < fin ≤ 12 mois | bleu |
| `DEPOT_URGENT` | fin ≤ 6 mois et aucun dépôt enregistré | orange |
| `CRITIQUE` | fin ≤ 3 mois et aucun dépôt enregistré | rouge |
| `EXPIRE` | fin < aujourd'hui | rouge foncé |
| `EN_INSTRUCTION` | dépôt enregistré, décision attendue | violet |

### 6.4 Règles d'alerte par défaut (paramétrables globalement et par pays)

| Code | Déclencheur | Destinataires | Canal |
|---|---|---|---|
| `J-365` | 12 mois avant la date de fin | Réglementaire pays | In-app |
| `J-180` | **6 mois avant : deadline de dépôt** | Réglementaire pays + Réglementaire siège | In-app + email |
| `J-90` | 3 mois avant, si non déposé | Réglementaire pays + siège (escalade) | In-app + email |
| `J-30` | 1 mois avant, si non déposé | Réglementaire pays + siège + CEO | In-app + email |
| `J0` | Expiration constatée | Tous les rôles concernés | In-app + email |
| `DECISION` | Renouvellement déposé depuis > N jours sans décision (N paramétrable, 120 par défaut) | Réglementaire pays | In-app |
| `DOSSIER` | Dossier « incomplet » sur une AMM à moins de 9 mois | Réglementaire pays | In-app |

Une alerte est **clôturée automatiquement** quand un renouvellement est enregistré comme déposé (pour `J-180`, `J-90`, `J-30`) ou obtenu (toutes). Une alerte peut être **acquittée** manuellement avec un commentaire.

### 6.5 Workflow de renouvellement

```
PLANIFIE → EN_PREPARATION → DEPOSE → EN_INSTRUCTION → OBTENU
                                                   ↘ REJETE → (nouveau renouvellement)
                        tout état → ABANDONNE (produit retiré du pays)
```
Le passage à `DEPOSE` exige une date de dépôt et, idéalement, un récépissé. Le passage à `OBTENU` exige le nouveau numéro d'AMM et la date de début ; la date de fin est calculée.

### 6.6 Unicité
Une AMM est identifiée par le couple (produit, pays). Un produit est identifié par son libellé normalisé ; les variantes de libellé du classeur sont conservées comme alias.

---

## 7. Fonctionnalités et user stories

### EPIC 1 — Authentification et droits
- **US1.1** En tant qu'utilisateur, je me connecte avec email + mot de passe ; ma session expire après 12 h d'inactivité.
- **US1.2** En tant que réglementaire siège, je crée un réglementaire pays, lui attribue ses pays, le désactive si besoin ; en tant que CEO, je gère aussi les comptes siège.
- **US1.3** Un `COUNTRY_REGULATORY` ne voit et ne modifie que ses pays ; un `HQ_REGULATORY` voit et modifie tous les pays ; un `CEO_ADMIN` a tous les droits.
- *Critères d'acceptation* : accès refusé (HTTP 403) hors périmètre ; toute action est journalisée.

### EPIC 2 — Référentiels
- **US2.1** Gérer les pays (code ISO, nom, autorité réglementaire, durée de validité, délai de dépôt, fuseau horaire).
- **US2.2** Gérer les gammes et les produits (libellé, gamme, DCI, dosage, forme, présentation, alias).
- **US2.3** Fusionner deux produits en doublon en conservant l'historique.

### EPIC 3 — Gestion des AMM
- **US3.1** Créer/modifier une AMM : produit, pays, numéro, date de début, date de fin calculée, état du dossier, commentaire.
- **US3.2** Ajouter un renouvellement avec son workflow et ses documents ; l'historique complet est visible sur une frise.
- **US3.3** Filtrer la liste par pays, gamme, statut, niveau d'urgence, état du dossier, texte libre ; trier par date de fin.
- **US3.4** Édition en ligne dans la grille pour les champs simples (date, numéro, état du dossier), à la manière d'Excel.
- **US3.5** Export Excel/CSV de la vue filtrée, avec le même format de colonnes que le classeur.
- *Critères d'acceptation* : les dates sont validées (JJ/MM/AAAA), un numéro d'AMM est une chaîne, le statut se met à jour instantanément pour tous les utilisateurs connectés.

### EPIC 4 — Alertes et notifications
- **US4.1** Recevoir une notification in-app (cloche + toast) dès qu'une alerte me concerne.
- **US4.2** Recevoir un email pour les alertes de niveau `J-180` et au-delà, avec lien direct vers l'AMM ; l'escalade J-90 atteint le siège, J-30 atteint le CEO.
- **US4.3** Recevoir chaque lundi 08:00 un digest par pays : alertes ouvertes, AMM à déposer sous 6 mois, dossiers incomplets.
- **US4.4** Acquitter une alerte, l'assigner à un collègue, y laisser un commentaire.
- **US4.5** Paramétrer les règles d'alerte (délai, destinataires, canal) globalement et par pays.
- *Critères d'acceptation* : une alerte n'est jamais envoyée deux fois pour la même AMM et la même règle ; le digest liste 0 élément si rien n'est ouvert et n'est alors pas envoyé.

### EPIC 5 — Temps réel
- **US5.1** Toute modification d'AMM, de renouvellement ou d'alerte est propagée en moins de 2 s à tous les navigateurs ouverts sur la même vue.
- **US5.2** Les compteurs du dashboard se rafraîchissent sans rechargement.
- **US5.3** Un indicateur affiche l'état de la connexion temps réel et se reconnecte automatiquement.

### EPIC 6 — Tableaux de bord
- **US6.1** Dashboard « Afrique » reprenant l'onglet Excel : par pays, total AMM, valides, expirées, en cours, indéterminées, % valides, expirant < 6 mois, < 12 mois, % dossiers complets, ligne TOTAL.
- **US6.2** Dashboard « Pays » : répartition par gamme et par statut, pipeline d'expiration mois par mois sur 24 mois, liste des priorités.
- **US6.3** Dashboard « Produit » : carte de couverture (dans quels pays le produit est autorisé, expiré, absent).
- **US6.4** Dashboards Grafana provisionnés pour la direction (métier) et l'exploitation (technique), sur une base PostgreSQL en lecture seule.

### EPIC 7 — Import et migration
- **US7.1** Importer le classeur Excel actuel via l'interface : détection des onglets normalisés, mapping des colonnes, normalisation des gammes et produits, prévisualisation, rapport des lignes en erreur (dates illisibles, doublons, numéros manquants).
- **US7.2** Réimport idempotent : une ligne déjà importée est mise à jour, pas dupliquée.
- **US7.3** Les onglets en ancien format (3 blocs par gamme) sont ignorés avec avertissement ; les onglets normalisés font foi.

### EPIC 8 — Gestion documentaire (AMM scannées)
- **US8.1** En tant que correspondant pays, je téléverse le scan PDF d'une AMM (origine ou renouvellement), d'un récépissé de dépôt ou d'un courrier de l'autorité ; je renseigne le type, la **date du document** (par défaut la date de début de l'AMM ou du renouvellement rattaché) et un titre facultatif.
- **US8.2** Le dossier documentaire d'une AMM est affiché en **chronologie inverse : du document le plus récent au plus ancien**, groupé par période d'autorisation (renouvellement N, N−1, …, AMM d'origine). Le document en tête est l'AMM en vigueur.
- **US8.3** Je consulte un PDF dans une visionneuse intégrée sans le télécharger ; je peux zoomer, naviguer par page et ouvrir le fichier dans un nouvel onglet.
- **US8.4** Je remplace un scan de mauvaise qualité par une nouvelle version ; l'ancienne version reste consultable dans l'historique du document, jamais supprimée physiquement.
- **US8.5** Je télécharge un document ou l'ensemble du dossier documentaire d'une AMM en archive ZIP, fichiers nommés `PAYS_PRODUIT_TYPE_AAAA-MM-JJ.pdf` et triés par date décroissante.
- **US8.6** Depuis la liste des AMM, un pictogramme indique si l'AMM en vigueur dispose de son scan ; un filtre « sans scan » permet de traiter les manques.
- **US8.7** Au niveau pays et produit, je consulte la bibliothèque documentaire complète, filtrable par type et par année, toujours triée du plus récent au plus ancien.
- **US8.8** Je consulte l'historique d'une AMM : qui a changé quoi, quand, avec l'ancienne et la nouvelle valeur, y compris les ajouts et remplacements de documents.
- *Critères d'acceptation* : seuls les PDF (et images JPG/PNG converties en PDF à l'import) sont acceptés, 25 Mo max par fichier ; l'ordre d'affichage est `date du document` décroissante puis `date de téléversement` décroissante ; l'accès aux fichiers respecte le périmètre pays ; un fichier ne peut être supprimé que par le CEO et reste archivé 5 ans.

---

## 8. Exigences non fonctionnelles

| Domaine | Exigence |
|---|---|
| Performance | Liste de 2 000 AMM filtrée et affichée en < 1 s ; dashboard < 2 s. |
| Temps réel | Latence de propagation < 2 s ; reconnexion automatique WebSocket. |
| Disponibilité | 99,5 % en heures ouvrées (Afrique de l'Ouest et Centrale). |
| Sécurité | HTTPS obligatoire, mots de passe hachés (Argon2), JWT courte durée + refresh token httpOnly, RBAC par pays, protection CSRF/XSS, limitation de débit sur l'authentification. |
| Confidentialité | Données hébergées sur une instance dédiée ; sauvegarde quotidienne chiffrée, rétention 30 jours. |
| Stockage documentaire | Fichiers PDF stockés hors base de données (volume chiffré ou stockage objet compatible S3), empreinte SHA-256 pour l'intégrité, sauvegarde incluse dans la sauvegarde quotidienne, capacité initiale 20 Go (1 548 AMM × 2 à 3 scans de 2 à 5 Mo). |
| Auditabilité | Historique complet des modifications sur AMM, renouvellements, alertes, référentiels. |
| Langue | Interface en français ; architecture i18n prête pour l'anglais. |
| Fuseaux | Dates stockées en UTC, affichées dans le fuseau du pays ; calcul quotidien en `Africa/Dakar`. |
| Accessibilité | Contrastes AA, navigation clavier dans la grille. |
| Compatibilité | Chrome, Edge, Firefox, Safari (2 dernières versions) ; responsive tablette. |
| Observabilité | Logs structurés, métriques Prometheus exposées et visualisées dans Grafana, alerting technique. |

---

## 9. Données : mapping du classeur vers le modèle

Onglets normalisés (format à 12 colonnes, ligne d'en-tête 2, données à partir de la ligne 3) :

| Colonne Excel | Champ cible | Traitement |
|---|---|---|
| `C GAMME` | `Product.range` | Normalisation : `GAMME GENERAL(E)` → Générale, `GAM(M)E CARDIO` → Cardio, `GAMME BIEN ETRE` → Bien-être |
| `D NOM` | `Product.name` + `ProductAlias` | Trim, majuscules, espaces multiples ; rapprochement avec le référentiel existant |
| `E DATE DEBUT` (AMM d'origine) | `Amm.original_start_date` | Date ; texte → tentative de parsing JJ/MM/AAAA, sinon anomalie |
| `F N° AMM` | `Amm.original_number` | Chaîne ; les flottants `.0` sont tronqués |
| `G DATE FIN` | `Amm.original_end_date` | Recalculée (+5 ans) ; si l'Excel diffère, l'Excel est conservé et signalé |
| `H DATE DEBUT` (renouvellement) | `Renewal.start_date` ou `Renewal.status=DEPOSE` si `IN PROCESS` | |
| `I N° AMM` | `Renewal.number` | Chaîne |
| `J DATE FIN` | `Renewal.end_date` | Recalculée |
| `K STATUT` | ignoré | Recalculé par l'application, comparé à l'Excel pour contrôle |
| `L ETAT DOSSIER` | `Amm.dossier_state` | `Dossier complet` → `COMPLET`, `Dossier incomplet` → `INCOMPLET`, vide → `INCONNU` |
| Nom d'onglet | `Country` | `CDI` → Côte d'Ivoire ; espaces finaux ignorés |

---

## 10. Roadmap

| Phase | Contenu | Durée indicative |
|---|---|---|
| **P0 — Fondations** | Monorepo, Docker, CI, auth, référentiels, modèle AMM, import Excel, liste et fiche AMM | 4 semaines |
| **P1 — Alertes** | Moteur de règles, Celery beat, emails, notifications in-app, WebSocket | 3 semaines |
| **P2 — Pilotage** | Dashboard Afrique/Pays/Produit, exports, Grafana provisionné, digest hebdo | 3 semaines |
| **P3 — Renouvellements et documents** | Workflow complet, gestion documentaire (upload PDF, chronologie inverse, visionneuse, ZIP), audit UI, édition en ligne | 4 semaines |
| **P4 — Mise en production** | Migration finale, formation, bascule, décommissionnement Excel | 2 semaines |
| V2 | Variations d'AMM, SMS/WhatsApp, multi-langue, API partenaires | — |

---

## 11. Risques et questions ouvertes

| Risque / question | Impact | Mitigation ou décision attendue |
|---|---|---|
| Durée de validité différente de 5 ans dans certains pays | Statuts faux | Paramètre par pays ; à confirmer pays par pays lors de l'import |
| Délai de dépôt réglementaire différent de 6 mois selon l'autorité | Alertes trop tardives | Paramètre par pays, valeur par défaut 6 mois |
| Qualité des données historiques (13 indéterminées, dates illisibles, doublons de libellés) | Migration incomplète | Rapport d'import + écran de correction ; validation par le responsable réglementaire |
| Connectivité limitée des correspondants locaux | Adoption | Interface légère, mode dégradé sans WebSocket (polling), emails comme canal de secours |
| Un produit peut-il avoir plusieurs AMM dans le même pays (présentations différentes) ? | Modèle de données | Hypothèse : une AMM par (produit, pays) ; la présentation fait partie du libellé produit. À confirmer |
| Hébergement (cloud ou serveur interne) et nom de domaine | Planning | Décision attendue avant P4 |
| Fournisseur email transactionnel (SMTP interne, SendGrid, Brevo…) | Alertes email | Décision attendue avant P1 |
