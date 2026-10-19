# Registre GHPL et dépôt des AMM

## 1. Import du registre GHPL (classement général des scans)

Le fichier `0_REGISTRE AMM GHPL.xlsx` du dossier Nextcloud « AMM GHPL - CLASSEMENT GENERAL » croise
le Dashboard AMM Afrique et les scans classés par gamme, pays et produit. Il s'importe au même endroit
que le Dashboard : **Imports Excel**. L'application le reconnaît à ses onglets `_Consolidation` et
`_Docs`.

Le Dashboard reste la référence. L'import du registre est donc prudent :

| Ligne du registre | Ce que fait l'import |
| --- | --- |
| AMM connue, n° ou date d'origine vides dans AMM GH | complète ces champs (jamais d'écrasement), tracé dans l'historique « Complété depuis le registre GHPL » |
| Statut dossier « Déposé » | ouvre un renouvellement **déposé**, daté de la dernière attestation de dépôt classée (`_Docs`), sauf si un dépôt ou une instruction est déjà en cours |
| « Classement seul » (absente du Dashboard) | crée l'AMM avec le n° et la date d'origine lus, notée « Présentation absente du Dashboard AMM Afrique » |
| « Acte classé plus récent que le Dashboard » | avertissement : importer le scan dans « Import de dossiers AMM » |
| AMM du Dashboard introuvable | avertissement : importer d'abord le Dashboard AMM Afrique à jour |
| Pays non suivi (RDC, Mauritanie) | avertissement |
| « PRÉSENTATION NON IDENTIFIÉE » | ignorée : rien n'est créé |

**Produits** : avant de créer un produit, l'import cherche le même produit écrit autrement, d'abord
parmi les produits suivis dans le pays, puis dans tout le catalogue :

- « OMEPRAL 20MG GELULE B28 » = « OMEPRAL 20MG GEL B/28 » ;
- « TENSOPLUS 2,5MG-10MG-10MG CPR B30 » = « TENSOPLUS 10MG/2,5MG/10MG CPR B/30 » ;
- « KETOPROFENE-GH » = « KETOPROFEN GH ».

Il faut la même marque, la même forme, les mêmes dosages et la même boîte quand elle est indiquée.
Quand deux fiches du catalogue sont des doublons (mêmes dosages, même boîte), c'est la plus utilisée
qui est reprise. Sinon le produit est créé, dans la gamme du registre.

**Conseil** : lancer d'abord en **simulation**. La page du lot ouvre sur les avertissements, avec un
filtre par résultat (erreurs, avertissements, créées, mises à jour, ignorées) et un résumé par pays.

**Durée** : l'import charge une fois produits, alias et AMM, puis ne lit plus rien en base ligne par
ligne. Il fait environ 2 000 requêtes au lieu de 9 000, et prend 7 s au lieu de 33 s en local
(plus sur Render gratuit). La page du lot affiche l'avancement : « 450 / 1814 lignes traitées ».
Un import coupé par un redémarrage du service passe en échec au bout de 45 min (« relancez-le ») au
lieu de rester « en cours ».

L'onglet « Parametres pays » (durées de validité, délais) n'est pas importé : ses valeurs sont des
hypothèses non confirmées.

Les scans du classement s'importent ensuite avec leur manifeste (section 1 bis).

## 1 bis. Import des scans classés (manifeste du classement)

Ordre : **Dashboard « version import AMM GH »**, puis **registre**, puis **scans**. Le dossier
`EXPORT AMM GH (application)` du classement contient `manifeste_scans_amm_gh.csv` : une ligne par
pièce (pays, présentation, période, type, date et sa fiabilité, n°, chemin, SHA-256). Seules les
3 628 pièces « Exemplaire principal = oui » sont prises (pas les doublons ni les pages séparées).

**Avant** : Administration > Pays, régler le Congo sur 4 ans (durée écrite sur les décisions) : les
renouvellements créés par l'import en dépendent. Les fiches existantes ne changent pas.

**1. Le manifeste dans Imports Excel** (simulation d'abord, puis pour de bon). Rien que des
métadonnées : chaque pièce reçoit sa place, et les fiches sont complétées.

| Pièce du classement | Ce que fait l'import |
| --- | --- |
| AMM introuvable | crée le produit (s'il manque) et l'AMM, avec le n° et la date d'origine |
| `1_AMM ORIGINE - AAAA` | date « haute » ou « lecture visuelle » de l'année AAAA : corrige la date d'origine ; autre date : complète seulement un champ vide ; les pièces d'autres années du dossier (courriers, attestations) ne comptent pas |
| `RENOUVELLEMENT n - AAAA-MM-JJ` | rapproché d'un renouvellement existant (même date, puis même n°, puis date à moins de 120 jours) et sa date corrigée ; sinon un dossier déposé sans décision est conclu ; sinon un renouvellement **obtenu** est créé |
| Dépôt, récépissé | avec le dossier en cours, ou le renouvellement qu'il a précédé (date de dépôt complétée) ; avant l'AMM d'origine : la demande d'origine ; sinon sur l'AMM (avertissement). Aucun dossier « déposé » n'est ouvert d'après un scan |
| Variation, rectificatif | période en vigueur à sa date |
| RCP, annexes | sur l'AMM |
| n° du classement | complète un n° vide, jamais plus (noms de dossiers, n° de décision, plages « 0139 a 0143 ») |

Garde-fou : si les corrections d'une AMM avançaient son échéance (ex. le Dashboard porte en
« origine » la décision de 2019, le classement n'a que l'AMM de 2009), elles ne sont pas appliquées ;
l'AMM est seulement complétée et un avertissement les liste. Les renouvellements sont renumérotés
dans l'ordre des dates : le dernier obtenu reste celui qui fixe l'échéance.

Répétition locale (Dashboard 13/10, registre, manifeste 13/10) : 3 608 pièces placées sur 3 628,
aucune erreur, 180 renouvellements créés, aucune échéance avancée, 43 échéances repoussées de
quelques jours à quelques mois par une date plus exacte. Restent à part : RDC et Mauritanie (pays
non suivis) et 5 pièces « présentation non identifiée ».

**2. Les fichiers**, depuis le Mac qui a le classement :

    python3 scripts/importer_scans_classement.py --classement "<…>/AMM GHPL - CLASSEMENT GENERAL"

Le script lit les places du dernier import du manifeste, vérifie le SHA-256 de chaque fichier et
l'envoie à sa fiche (`POST /amms/{id}/documents`). Il peut être arrêté et relancé
(`importer_scans_etat.json`). Laissés de côté et listés dans le rapport CSV : les fichiers modifiés
depuis le manifeste, les `.docx` sans LibreOffice, les fichiers de plus de 25 Mo (4) et les formats
refusés. Les aperçus sont générés ensuite, un par un, par le service.

## 2. Rubrique « Dépôts AMM » : le renouvellement du siège au pays

Menu **Dépôts AMM** (`/depots`). Un dossier de dépôt suit un renouvellement de bout en bout. Le
siège et le pays y travaillent chacun à leur tour, et chacun est prévenu quand c'est à lui.

| Étape | Qui | Ce qui se passe dans l'application |
| --- | --- | --- |
| 1. Montage du dossier | Siège | Joindre les pièces demandées pour le pays (PDF, Word, Excel, photo) |
| 2. Échantillons | Siège | Noter chaque lot : n° de lot, date de fabrication, date de péremption, quantité |
| 3. Envoi au pays | Siège | « Envoyer au pays » (refusé tant qu'il manque une pièce obligatoire ou les échantillons), avec un message. Le pays reçoit une notification |
| 4. Dépôt à l'agence | Pays | Télécharger le dossier (ZIP), le déposer, puis saisir la date de dépôt et joindre l'attestation. Le siège est prévenu |
| 5. Commission | Pays ou siège | Noter chaque passage en commission, notification ou demande de complément (avec pièce) |
| 6. Décision | Pays ou siège | Obtenu (n°, date de début, scan de la décision) ou rejeté. Le dossier est clos |

**Le renouvellement suit le dossier** : l'étape n'est jamais saisie, elle se déduit du
renouvellement lié, qui passe par sa machine d'états habituelle (historique, recalcul de l'AMM,
temps réel).

- Ouvrir un dossier planifie le renouvellement s'il n'existe pas, puis le passe « en préparation ».
- L'attestation le passe « déposé » (date de dépôt). Elle est rangée dans les documents de l'AMM
  (type récépissé).
- Le premier passage en commission le passe « en instruction ».
- La décision obtenue crée l'échéance suivante et range le scan comme décision d'AMM.
- Un renouvellement conclu ailleurs (fiche AMM, import de dossier) clôt aussi le dossier.

**Le ZIP du pays** reprend l'ordre du dossier papier :

- `00 - Bordereau du dossier.pdf` : pièces, échantillons, consignes et message du siège ;
- puis un dossier par pièce : `01 - Lettre de demande de renouvellement/…`, etc.

Chaque téléchargement est tracé. Le premier téléchargement par le pays prévient le siège.

**Échanges siège ↔ pays** : chaque dossier a son fil de messages. Un message du siège prévient le
réglementaire du pays, et un message du pays prévient le siège. Le journal garde toutes les
actions.

**À préparer** (siège) : les AMM dont l'échéance tombe dans l'année, ou expirées depuis moins d'un
an, et qui n'ont pas de dossier ni de dépôt en cours. Un clic ouvre le dossier. La fiche AMM propose
aussi « Monter le dossier de dépôt », ou le lien vers le dossier existant.

**Pièces demandées** (siège, `/depots/pieces`) :

- **liste de base** : lettre de demande, certificat de PGHT (prix grossiste hors taxe), formulaires, RCP, certificats
  d'analyse et pièces réglementaires (facultatives) ;
- **par pays** : décocher une pièce de base que le pays ne demande pas, ou ajouter une pièce propre
  au pays ;
- une pièce retirée alors qu'elle est déjà jointe à des dossiers est seulement désactivée.

### Droits

| Action | Siège, CEO | Réglementaire pays |
| --- | --- | --- |
| Voir les dossiers | tous | ceux de ses pays |
| Ouvrir, monter, envoyer, abandonner | oui | non |
| Télécharger le dossier | toujours | une fois envoyé |
| Dépôt, commission, décision, messages | oui | oui |

### API

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET, POST | `/api/v1/deposits` | dossiers visibles ; POST `{amm}` ouvre le dossier (siège) |
| GET | `/api/v1/deposits/suggestions` | AMM à préparer |
| GET | `/api/v1/deposits/{id}` | dossier complet (pièces, échantillons, suivi, messages, journal, droits) |
| POST, DELETE | `/api/v1/deposits/{id}/pieces[/{piece}]` | joindre (multipart `file`, `piece_type` ou `label`) / retirer une pièce |
| POST, DELETE | `/api/v1/deposits/{id}/samples[/{sample}]` | échantillons |
| POST | `/api/v1/deposits/{id}/samples-required` | `{required}` |
| POST | `/api/v1/deposits/{id}/send` | envoi au pays `{note}` |
| GET | `/api/v1/deposits/{id}/archive` | ZIP du dossier (téléchargement tracé) |
| POST | `/api/v1/deposits/{id}/deposit` | `filing_date` + attestation (multipart) |
| POST | `/api/v1/deposits/{id}/events` | `kind` (COMMISSION, NOTIFICATION, COMPLEMENT, AUTRE), `date`, `note`, `file` |
| POST | `/api/v1/deposits/{id}/decision` | `result` (OBTENU, REJETE), `decision_date`, `number`, `start_date`, `file` |
| POST | `/api/v1/deposits/{id}/abandon` | `{reason}` (siège) |
| POST | `/api/v1/deposits/{id}/messages` | `{body}` |
| CRUD | `/api/v1/deposit-pieces` | pièces demandées (écriture : siège) |

L'événement temps réel `deposit.updated` (groupe du pays) rafraîchit les dossiers ouverts.
