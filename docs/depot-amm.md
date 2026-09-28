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

L'onglet « Parametres pays » (durées de validité, délais) n'est pas importé : ses valeurs sont des
hypothèses non confirmées.

Les scans du classement (plus de 3 600 documents) s'importeront ensuite par « Import de dossiers
AMM », une fois synchronisés depuis Nextcloud.

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

- **liste de base** : lettre de demande, certificat de PGHT, formulaires, RCP, certificats
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
