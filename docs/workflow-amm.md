# Workflow d'une AMM : origine, renouvellements, statuts et rappels

Ce document décrit, en français simple, les règles métier fixées par le responsable et leur
traduction dans le code. Il fait foi pour le calcul du statut, des dates de dépôt, de l'état du
dossier et du rappel quotidien.

## 1. Origine et renouvellements

Chaque AMM commence par une **origine** (la première décision, avec sa date de début et sa date
de fin). Elle peut ensuite recevoir zéro, un ou plusieurs **renouvellements** successifs,
rattachés à la même AMM.

Un renouvellement n'est pris en compte **que lorsqu'il est OBTENU** (et qu'il porte une date de
fin). Tant qu'il est planifié, en préparation, déposé ou en instruction, il décrit l'avancement
du dossier de renouvellement : il ne change ni la date de fin, ni le statut de l'AMM.

## 2. Document actuel et date de fin

- **Document actuel** = la décision d'origine s'il n'y a aucun renouvellement obtenu, sinon le
  **dernier renouvellement obtenu**.
- La **date de fin de l'AMM actuelle** (`effective_end_date`) est la date de fin de ce document.
  Tout le suivi des échéances repose sur elle.

## 3. Statuts

| Statut | Quand | Couleur |
| --- | --- | --- |
| **Valide** (`VALIDE`) | la date de fin est à plus de six mois | vert |
| **À renouveler** (`A_RENOUVELER`) | on est dans les six mois précédant la fin (jour J compris) ; l'AMM reste valide | orange |
| **Expirée** (`EXPIRE`) | aujourd'hui est après la date de fin | rouge |
| **Échéance inconnue** (`INDETERMINE`) | aucune date de fin connue — donnée manquante, pas une situation métier | gris |

Précisions :

- le jour de la date de fin, l'AMM est encore valide (« À renouveler ») ; le lendemain, elle est
  **Expirée**, automatiquement ;
- une AMM expirée n'est jamais « À renouveler » ;
- **un dépôt en cours n'empêche pas l'expiration** : l'ancien statut « En cours d'instruction »
  n'existe plus. L'avancement d'un renouvellement (Planifié / Déposé / En instruction) reste
  visible sur le renouvellement lui-même, jamais comme statut de l'AMM.

## 4. Dates de dépôt et rappel quotidien

À partir de la date de fin :

- **Dépôt idéal** (`ideal_filing_date`) = fin − 6 mois : objectif interne ;
- **Limite agence** (`agency_filing_deadline`) = fin − 3 mois : date limite de l'autorité.

Dès que l'AMM est « À renouveler », un **rappel quotidien** part vers les réglementaires
concernés (siège et réglementaires du pays de l'AMM) : notification dans l'application, et
e-mail si le canal est activé (`RENEWAL_REMINDER_CHANNELS`, par défaut `IN_APP,EMAIL`). Le texte
nomme le produit, le pays, « expire le … », « Dépôt idéal : … » (ou « dépassé ») et
« Limite agence : … » (ou « dépassée »).

Le rappel est **idempotent** : au plus un par AMM, par destinataire, par canal et par jour
(contrainte unique en base). Il s'arrête tout seul quand l'AMM n'est plus « À renouveler » :
soit un renouvellement obtenu repousse la date de fin, soit l'AMM expire.

Tâche : `apps.notifications.tasks.send_renewal_reminders`, planifiée chaque jour à 07:30
(Celery beat, `CELERY_BEAT_SCHEDULE`), après le recalcul nocturne des statuts (00:05).

Les **règles d'alerte** existantes (J-365, J-180, J-90, J-30, J0, DOSSIER, DECISION) sont
conservées telles quelles et restent désactivables dans « Règles d'alerte ».

## 5. Urgence (indicateur de tri)

L'urgence sert aux listes de priorités et aux tableaux de bord ; elle suit les mêmes dates :

- `EXPIRE` : AMM expirée ;
- `CRITIQUE` : limite agence atteinte ou dépassée ;
- `DEPOT_URGENT` : dépôt idéal atteint ou dépassé (donc « À renouveler ») ;
- `A_PLANIFIER` : échéance dans un an ou moins, ou échéance inconnue ;
- `OK` : le reste.

Un dépôt en cours ne masque plus l'urgence (l'ancien niveau « En instruction » a disparu).

## 6. État du dossier

Le dossier est **complet** quand le **scan de la décision actuelle** (origine ou dernier
renouvellement obtenu) est rattaché à l'AMM, **incomplet** sinon. Il est totalement indépendant
de la validité : une AMM expirée dont la décision est scannée reste « Dossier complet ».

## 7. Qui saisit quoi

Les réglementaires téléversent les décisions et enregistrent les renouvellements. Tout le reste
— statut, urgence, dates de dépôt, état du dossier, alertes, rappels — est calculé.

## 8. Import d'un dossier : on dépose, c'est rangé

Menu « Import de dossiers » : le réglementaire dépose le dossier reçu (décision d'origine,
décisions de renouvellement, courriers), et c'est fini. L'application :

1. **trouve l'AMM** (produit + pays) à partir des décisions et du nom du dossier ;
2. **range chaque scan à sa période** : AMM d'origine, ou renouvellement n ;
3. **crée les renouvellements obtenus** lus sur les décisions (numéro et date de début lisibles ;
   date de fin lue, sinon déduite comme d'habitude : début + durée de validité du pays) ;
4. **complète les champs vides** de la fiche (titulaire, n°, dates…) ;
5. **recalcule** statut, échéance et complétude (règles des sections 2 à 6) ;
6. **prévient** l'auteur, le siège et les réglementaires du pays (notification avec le bilan).

Rien à valider, pas de pourcentage de confiance à interpréter : si l'AMM est identifiée, le dossier
est rangé automatiquement (« Rangé automatiquement »).

### Points à vérifier plus tard

Quand un scan ne dit pas la même chose que la fiche sur une valeur **déjà renseignée**, l'import
**garde la valeur de la fiche**, range quand même le scan et note un **point à vérifier plus
tard**. Jamais bloquant, jamais d'écrasement automatique. Même chose pour :

- un renouvellement lu qui entre en conflit avec un renouvellement déjà enregistré (même période) :
  la fiche est gardée ;
- une décision sans date ni numéro lisibles, ou dont on ne sait pas la période : le scan est rangé
  comme « autre document » de la fiche ;
- deux décisions du dossier qui se contredisent, un n° d'AMM mal lisible ou déjà attribué, un
  document lu en partie.

Les points apparaissent sur la **fiche AMM** (encadré « Points à vérifier plus tard », au-dessus
des onglets ; un badge dans la liste des AMM en donne le nombre) et sur la page du lot. Pour chacun :
**Voir le scan**, puis **Appliquer la valeur du scan** (la fiche est corrigée, tracée dans
l'historique avec le scan en preuve) ou **Ignorer**. Réimporter le même dossier ne recrée ni
document, ni renouvellement, ni point déjà traité.

### Le seul cas où l'import pose une question

Uniquement quand l'AMM cible **n'est pas identifiable** : produit non reconnu ou absent du
catalogue, produit sans AMM dans le pays, plusieurs AMM possibles, pays inconnu ou hors de votre
périmètre. Le lot affiche alors **« Question : c'est quelle AMM ? »** : choisissez l'AMM (recherche
par produit, limitée au pays du dossier et à votre périmètre) puis **« Ranger les documents
ici »** ; le dossier est relu et rangé automatiquement sur cette AMM.

L'import ne crée jamais d'AMM ni de produit tout seul. Quand l'AMM n'existe pas encore et que la
décision d'origine est lisible, le siège peut la créer depuis le lot (bouton secondaire, avec
confirmation).

### « Voir le scan »

Les scans sont servis depuis le stockage permanent (Cloudflare R2). Un lot déposé avant sa mise en
place peut avoir perdu ses fichiers : l'écran affiche alors « Fichier perdu (stocké avant la mise en
place du stockage permanent) : réimportez ce dossier. » Si le scan avait déjà été rangé dans la
fiche, c'est la copie rangée qui est montrée.

### Dossier pays ou gamme entier

On peut déposer un dossier produit, un dossier pays (« CAMEROUN ») ou un dossier gamme
(« CARDIO AFRIQUE », qui contient les pays). L'application crée un import par **dossier de
présentation**, c'est-à-dire le dossier qui contient les documents. Ses sous-dossiers de période
(« ORIGINE », « RENOUVELLEMENT 2020 ») restent avec lui.

- Un document posé au-dessus des dossiers produits, par exemple une décision groupée à la racine
  du pays, est joint à chaque produit en dessous, dans « Documents communs ». Il n'est gardé
  dans la fiche d'un produit **que s'il le concerne** (voir « Décisions groupées ») ; sinon il
  est listé dans les détails de la lecture comme « laissé de côté », sans point à vérifier.
- Les documents communs ne disent ni le pays ni le produit du dossier : l'identité vient des
  documents du produit lui-même.
- Importer de préférence depuis « PRÊT À IMPORTER » : les copies y portent déjà leur texte, la
  lecture est immédiate. Les scans d'origine passent par l'OCR, très lent sur Render gratuit.
- Les fichiers que l'import ne lit pas (xls, zip, docx, alias macOS) et ceux de plus de 25 Mo
  sont mis de côté et listés. Le reste du dossier part quand même.

### Décisions des différents pays

| Pays | Ce qui est lu |
|---|---|
| Cameroun, Gabon | « Décision N° … », « Registration number », « à partir du … » |
| Sénégal | « Sous le numéro : 7897 », « Numéro AMM : … du … au … », tampon d'enregistrement de l'arrêté « 15.04.2026*009037 » (date de décision) |
| Mali | « renouvelée sous le numéro 0374R/09/2020 … à compter du 1er juin 2020 » (le nouveau numéro, pas l'ancien) ; « … suivant Décision ministérielle N° 2024-0000675/MSDS-SG du 15 avril 2024 » (numéro et date de l'AMM) ; « DECISION N° 2022-002328 … portant autorisation de mise sur le marché » (le numéro de décision est le numéro d'AMM) ; validité « à compter de la date de signature » (le début est la date de signature) |
| Gambie | « Registration number / Registration date / Registration expiry date » |
| Togo | « SP.TG 5223 » |
| Bénin | « visa de commercialisation », « N° AMM_2019_4848_EG », « COTONOU, le 16 AVR 2019 » |
| Congo | « DECISION N° CV/04C-07G/09 portant homologation » (le numéro de décision est le numéro d'AMM) |
| Niger | date de l'avis de la commission nationale d'homologation |
| Côte d'Ivoire, Guinée, Tchad | décisions groupées en tableau (voir ci-dessous) ; en Côte d'Ivoire la dénomination est sur la ligne au-dessus du numéro (« AMLO VH 5 mg/… » puis « comprimés pelliculés E-2015-418 ») |
| Mauritanie | ATI (autorisation temporaire d'importation) : pièce annexe, jamais une preuve d'AMM |

La date de signature (« Bamako, le 24 SEP 2020 », « Fait à Dakar, le … », « CORONOU, le … » mal lu)
sert de date de décision. Les mois abrégés (« AVR », « Déc. »), les ordinaux (« 1er », « 22nd ») et
les tampons lus chiffre par chiffre (« le 2 9 DEC 2023 ») sont reconnus. Une date de signature
future (« 21 OCT 2071 ») est une lecture fautive : elle est écartée.

Le pays se lit sur son **nom** (« République du Mali », « BURKINA », « Côte d'Ivoire »), jamais sur
le code à deux lettres dans le texte : « 100 mg » n'est pas Madagascar ni « ne … pas » le Niger. Un
dossier nommé du seul code (« SN/… ») reste reconnu. Une « notification provisoire » ou un « avis
favorable » de la commission n'est pas encore l'AMM : pièce annexe.

Deux numéros qui ne diffèrent que par les espaces ou les zéros de tête (« E-2015-0418 » dans la
fiche, « E-2015- 418 » sur le scan) sont le même numéro : pas de point à vérifier.

### Décisions groupées

Une décision peut accorder ou renouveler des dizaines de produits d'un coup (tableau
« Dénomination | N° AMM | Date »). L'import lit le tableau, que l'OCR le restitue ligne par ligne
ou colonne par colonne. Il ne retient que **la ligne du produit du dossier**, pour son numéro et
sa date. Si le produit n'y figure pas, la décision est rangée comme pièce annexe et un point à
vérifier le signale — sauf si c'est un document commun du dossier pays : il est alors laissé de
côté.

Un **recueil de décisions** réunit plusieurs décisions complètes, une par spécialité (Mali :
« AMM groupée 23 DEC 2023 », six décisions de deux pages ; « Renouvellement AMM 15 PRODUITS
2019 », une page par produit). L'import le découpe en sections, d'après « … pour la spécialité :
GENSET 10 mg … », lit **la seule section du produit** (numéro, dates, origine ou renouvellement) et
ne range dans la fiche **que ses pages** (« AMM groupée 23 DEC 2023.pdf (p. 3-4) »). Une même
marque relue deux fois dans une décision n'en fait pas un recueil.

Reprise : les dossiers pays rangés avant le 26/09/2026 avaient reçu dans chaque fiche tous les
documents de la racine du pays. Au déploiement, ceux qui ne concernent pas la fiche sont archivés
(jamais supprimés) et leurs points à vérifier fermés (`manage.py nettoyer_documents_communs
--dry-run` pour lister).

## 9. Où c'est écrit dans le code

| Quoi | Où |
| --- | --- |
| Calcul du statut, des dates et de l'état du dossier | `backend/apps/amm/services/status.py` |
| Champs stockés (`status`, `urgency`, `effective_end_date`, `ideal_filing_date`, `agency_filing_deadline`, `dossier_state`) | `backend/apps/amm/models.py` |
| Recalcul nocturne | `apps.amm.tasks.recompute_all_statuses` |
| Rappel quotidien « À renouveler » | `backend/apps/notifications/reminders.py` |
| Règles d'alerte | `backend/apps/alerts/` |
| Import de dossier : plan de rangement, question « quelle AMM ? », points à vérifier | `backend/apps/imports/dossier/preview.py` |
| Rangement automatique (après l'analyse) | `backend/apps/imports/tasks.py`, `backend/apps/imports/dossier/application.py` |
| Points à vérifier : appliquer la valeur du scan / ignorer | `backend/apps/imports/dossier/review_points.py` |
| Résultat prévu d'un lot (statut, échéance, complétude) | `backend/apps/imports/dossier/projection.py` |
| Miroir côté interface (libellés, couleurs, `statusFor`, `filingDates`) | `frontend/src/lib/urgency.ts` |

## 10. Algorithme, en une page

```
renouvellements_obtenus = renouvellements où statut = OBTENU et date de fin renseignée
document_actuel        = le plus récent des renouvellements obtenus, sinon l'origine
fin                    = date de fin du document actuel

si fin est inconnue        -> INDETERMINE (« Échéance inconnue »)
sinon si aujourd'hui > fin -> EXPIRE
sinon si aujourd'hui >= fin − 6 mois -> A_RENOUVELER
sinon                      -> VALIDE

dépôt idéal   = fin − 6 mois
limite agence = fin − 3 mois

dossier = COMPLET si le scan (kind=AMM, courant) du document actuel est rattaché, sinon INCOMPLET
```
