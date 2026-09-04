# Étude de faisabilité fonctionnelle — AMM INNOV

| Champ | Valeur |
|---|---|
| Version | 1.0 |
| Date | 04/09/2026 |
| Documents liés | [PRD](../prd.md) · [Conception](conception.md) · [Faisabilité non fonctionnelle](faisabilite-non-fonctionnelle.md) |

## 1. Objet

Vérifier que les besoins exprimés dans le PRD peuvent être couverts par une application web, à partir des données réellement disponibles dans le classeur `Dashboard AMM Afrique 18_08_2026 version 2.1.xlsx`, avec les trois acteurs identifiés, et identifier les points qui exigent une décision métier avant le développement.

## 2. Acteurs

| Acteur | Rôle applicatif | Responsabilités | Périmètre de données |
|---|---|---|---|
| **Réglementaire pays** | `COUNTRY_REGULATORY` | Constitue et dépose les dossiers d'AMM et de renouvellement auprès de l'autorité nationale ; saisit les numéros, dates et scans ; suit les alertes ; met à jour l'état du dossier. | Uniquement les pays qui lui sont affectés. |
| **Réglementaire siège** | `HQ_REGULATORY` | Coordonne les activités réglementaires de tous les pays ; crée et gère les comptes des réglementaires pays et leurs affectations ; arbitre les priorités ; paramètre les règles d'alerte ; lance les imports ; contrôle la qualité des données. | Tous les pays, tous les produits. |
| **CEO** | `CEO_ADMIN` | Administrateur de l'application ; vue d'ensemble : couverture réglementaire par pays et par gamme, risques de rupture, performance des équipes ; gère les comptes siège ; seul habilité à supprimer un document. | Tout, sans restriction. |

Acteurs secondaires (systèmes) : serveur de messagerie (emails d'alerte), stockage de fichiers (scans PDF), Grafana (restitution), planificateur (traitements nocturnes).

## 3. Analyse de l'existant

### 3.1 Ce que le classeur permet déjà
- Recenser 1 548 AMM sur 15 pays avec numéro, dates d'origine et de dernier renouvellement.
- Calculer un statut (valide, expiré, en cours, indéterminé) et des compteurs par pays.
- Signaler les AMM expirant sous 6 et 12 mois.

### 3.2 Ce qu'il ne permet pas
| Besoin | Couvert par Excel | Commentaire |
|---|---|---|
| Alerter automatiquement 6 mois avant expiration | Non | Aucune notification ; dépend de la consultation du fichier |
| Suivre l'avancement d'un dépôt de renouvellement | Non | Seule la mention « IN PROCESS » existe, sans date ni étape |
| Conserver l'historique des renouvellements successifs | Non | Un seul « dernier renouvellement » est stocké |
| Stocker les scans des AMM | Non | Documents dispersés (emails, disques locaux) |
| Travailler à plusieurs, par pays, avec des droits | Non | Un fichier unique, aucune restriction |
| Tracer qui a modifié quoi | Non | |
| Garantir la qualité de saisie | Partiellement | Validations de dates présentes mais contournées (dates en texte, numéros en flottant) |

## 4. Faisabilité par domaine fonctionnel

Échelle : **Acquise** (aucune incertitude), **Acquise sous condition** (décision ou donnée à confirmer), **À prototyper**.

| # | Domaine | Faisabilité | Justification | Conditions / décisions |
|---|---|---|---|---|
| F1 | Référentiels pays, gammes, produits | Acquise | Données présentes dans le classeur ; 15 pays, 3 gammes, ~300 produits après normalisation | Validation par le siège de la liste de produits dédoublonnée (856 libellés bruts) |
| F2 | Gestion des AMM (origine + renouvellements historisés) | Acquise | Le format normalisé à 12 colonnes se transpose directement ; l'historique complet sera reconstitué à partir de la date d'import puis alimenté au fil de l'eau | Hypothèse : une AMM par couple produit × pays |
| F3 | Calcul automatique du statut | Acquise | Formule Excel entièrement transcrite (`compute_amm_state`), testable par table de cas ; contrôle de non-régression sur les totaux du classeur (963 / 501 / 71 / 13) | Confirmer la durée de validité (5 ans) pays par pays |
| F4 | Alerte de dépôt à 6 mois et escalades | Acquise | Dépend uniquement de la date de fin effective, disponible pour 1 535 AMM sur 1 548 | Délai de dépôt par pays à confirmer (6 mois par défaut) ; désigner les destinataires par pays |
| F5 | Workflow de renouvellement | Acquise sous condition | Les étapes (préparation, dépôt, instruction, décision) sont universelles ; les délais d'instruction varient selon l'autorité | Valider la liste des étapes avec les réglementaires pays ; définir le délai « décision en retard » par pays |
| F6 | Notifications in-app et email | Acquise | Technologies standard ; canaux SMS/WhatsApp reportés | Choisir le fournisseur SMTP |
| F7 | Temps réel multi-utilisateurs | Acquise | WebSocket avec repli en polling ; volume faible (dizaines d'utilisateurs) | Connectivité des correspondants pays : mode dégradé prévu |
| F8 | Tableaux de bord (Afrique, pays, produit) | Acquise | Reprise à l'identique de l'onglet DASHBOARD ; agrégats simples | — |
| F9 | Gestion documentaire des scans PDF, chronologie inverse | Acquise | Stockage fichier + métadonnées ; tri par date du document ; volumétrie estimée 20 Go | Récupérer les scans existants ; définir la date à retenir sur les documents anciens sans date lisible (par défaut date de début de l'AMM) |
| F10 | Import du classeur et rapport d'anomalies | Acquise | Parseur validé sur le fichier réel ; anomalies attendues : 13 statuts indéterminés, dates texte, doublons de libellés | Une session de correction des anomalies par le siège avant bascule |
| F11 | Gestion des comptes par le siège | Acquise | Le siège crée les réglementaires pays et leur affecte des pays ; le CEO gère les comptes siège | Politique de mots de passe et durée de session |
| F12 | Journal d'audit | Acquise | Historisation de chaque modification avec auteur | — |
| F13 | Exports Excel/CSV au format du classeur | Acquise | Colonnes identiques pour faciliter la transition | — |
| F14 | OCR des scans, extraction automatique des dates | À prototyper (V2) | Qualité variable des scans ; hors MVP | — |
| F15 | Variations d'AMM (changements de formule, de site) | Hors périmètre MVP | Non présent dans le classeur | À cadrer pour la V2 |

## 5. Cas d'utilisation principaux et couverture

| Cas d'utilisation | Acteur principal | Précondition | Résultat |
|---|---|---|---|
| Déposer un renouvellement | Réglementaire pays | AMM existante dans son périmètre, alerte J-180 ouverte ou non | Renouvellement en état `DEPOSE`, alerte résolue automatiquement, siège notifié |
| Enregistrer une AMM obtenue | Réglementaire pays | Renouvellement déposé | Nouveau numéro, nouvelles dates, statut `VALIDE`, scan PDF rattaché en tête de chronologie |
| Traiter une alerte | Réglementaire pays | Alerte ouverte | Alerte acquittée ou assignée avec commentaire |
| Consulter le dossier documentaire | Tous | AMM existante | Liste des scans du plus récent au plus ancien, visionneuse |
| Coordonner les priorités | Réglementaire siège | — | Vue consolidée, réassignation d'alertes, relance |
| Gérer un réglementaire pays | Réglementaire siège | — | Compte créé, pays affectés, droits effectifs immédiatement |
| Paramétrer les règles d'alerte | Réglementaire siège | — | Règles globales et par pays actives au prochain traitement nocturne |
| Importer le classeur | Réglementaire siège | Fichier au format normalisé | AMM créées ou mises à jour, rapport d'anomalies |
| Piloter la couverture réglementaire | CEO | — | Dashboard Afrique, Grafana, exports |
| Administrer l'application | CEO | — | Comptes siège, suppression de documents, paramètres globaux |

Le diagramme de cas d'utilisation détaillé figure dans [conception.md](conception.md).

## 6. Données : disponibilité et qualité

| Donnée | Disponible | Qualité | Action |
|---|---|---|---|
| Pays | Oui (15) | Bonne | Compléter autorité, durée de validité, délai de dépôt |
| Gamme | Oui | Libellés hétérogènes (5 variantes) | Normalisation automatique |
| Produit | Oui | 856 libellés pour ~300 produits | Normalisation + alias + validation manuelle |
| Numéro d'AMM | Oui | Formats hétérogènes, flottants au Cameroun | Conversion en chaîne |
| Date de début d'origine | 1 535 / 1 548 | Quelques dates en texte | Parsing, sinon anomalie à corriger |
| Renouvellement | Partiel | Un seul niveau conservé | Historique reconstruit à partir de l'import |
| État du dossier | Oui | Renseigné à 95 % | Valeur `INCONNU` sinon |
| Scans PDF | Non dans le classeur | À collecter | Campagne de collecte par pays pendant la phase P3 |

## 7. Contraintes organisationnelles

- Les réglementaires pays ne sont pas tous salariés du siège (partenaires locaux) : les comptes doivent pouvoir être limités strictement à leurs pays et désactivés rapidement.
- Le siège doit pouvoir agir « au nom » d'un pays en cas d'absence du correspondant : `HQ_REGULATORY` a les droits d'écriture sur tous les pays.
- Le CEO a besoin d'une lecture immédiate sans formation : le dashboard Afrique reprend visuellement le classeur connu.

## 8. Risques fonctionnels

| Risque | Probabilité | Impact | Réponse |
|---|---|---|---|
| Règles de validité ou de dépôt différentes selon les pays | Élevée | Alertes fausses | Paramètres par pays, atelier de validation avec chaque correspondant |
| Résistance au changement (habitude d'Excel) | Moyenne | Adoption lente | Grille éditable proche d'Excel, exports au même format, formation |
| Données historiques incomplètes (scans absents) | Élevée | Dossier documentaire partiel au départ | Indicateur « scan manquant » et campagne de collecte |
| Double saisie pendant la transition | Moyenne | Divergences | Bascule franche après import validé, classeur figé en lecture seule |

## 9. Conclusion

Toutes les fonctionnalités du MVP sont réalisables avec les données existantes. Trois décisions métier conditionnent la justesse des alertes et doivent être prises avant la fin de la phase P1 : durée de validité par pays, délai de dépôt par pays, liste des étapes du workflow de renouvellement. La collecte des scans PDF existants est le principal travail non technique à planifier.
