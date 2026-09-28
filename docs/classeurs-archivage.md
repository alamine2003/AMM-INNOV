# Classeurs d'archivage (classeurs 3D)

Chaque classeur papier des AMM a son jumeau dans AMM GH (menu **Classeurs**). L'archiviste feuillette le papier
et l'écran en même temps. Pour chaque page, il constate : **Conforme**, **Corriger** (il saisit la valeur lue
sur le papier) ou **Absent du classeur**.

## Les classeurs

- **Sénégal (siège)** : 4 classeurs, un par gamme (Générale A-K, Générale L-Z, Cardio, Bien-être). La Générale
  est coupée selon la première lettre du produit.
- **Autres pays** : un classeur par pays, avec un intercalaire par gamme présente, dans l'ordre Générale,
  Cardio, Bien-être.
- **Ordre des pages** : une page par AMM, triée de A à Z par nom de produit (sans tenir compte des accents).
  C'est l'ordre des classeurs papier, pas celui des lignes de l'Excel.
- **Mise à jour** : rien n'est stocké. Les classeurs se recalculent depuis les AMM : une nouvelle AMM prend
  sa place, et un produit qui change de gamme change de classeur.

Pour découper un autre pays en plusieurs classeurs, modifier `SPLIT_COUNTRIES` dans
`backend/apps/binders/layout.py`.

## Qui voit quoi

| Rôle | Classeurs | Vérifier | PDF |
| --- | --- | --- | --- |
| Réglementaire pays | ceux de ses pays uniquement (les autres répondent 404) | oui | non |
| Siège, CEO | tous | oui | oui |

## Ce que fait un constat

- **Conforme** : la page est tamponnée « Vérifié ». Les écarts ouverts de l'import sur cette AMM sont refermés :
  « valeur du scan appliquée » si la fiche porte déjà la valeur du scan, « ignoré » sinon.
- **Corriger** : la valeur lue sur le papier remplace celle de la fiche. L'historique garde l'ancienne valeur,
  l'auteur et le motif « Vérifié sur le classeur papier ». Un renouvellement présent sur le papier mais absent
  de l'application est créé au statut « obtenu ». Une date de fin antérieure à la date de début est refusée.
- **Absent du classeur** : le dossier papier est à retrouver.
- **À scanner** : calculé automatiquement quand le papier est présent mais que la décision en vigueur n'a pas
  de scan.
- **Pages en trop** : dossier présent dans le classeur papier sans AMM dans l'application. On le signale sur
  la dernière feuille (Bilan).
- **Annuler le constat** : remet la page « à vérifier ». Les valeurs déjà corrigées restent en place.

## Interface

- **Étagère** : les classeurs debout, avec leur avancement. Le siège a un bouton de téléchargement sous chaque
  classeur.
- **Classeur ouvert** :
  - une feuille perforée par AMM, avec les onglets de gamme sur la tranche et le mécanisme à levier ;
  - les pages se tournent en 3D, et le mode rapide se règle avec le bouton « Animation » ;
  - navigation : flèches ←/→, glisser du doigt, coin corné ou curseur en bas ;
  - raccourcis : **C** conforme, **E** corriger, **A** absent. Après un constat, la page se tourne seule ;
  - le classeur s'ouvre à la première page pas encore vérifiée.
- **Filtres** : « Toutes les pages », « Pas encore vérifiées » ou « Écarts et manques » (écart avec le scan,
  pas de scan, n° ou date d'origine manquants). Le filtre est figé à son choix : une page que l'on vient de
  vérifier ne disparaît pas.
- **PDF (siège)** : dans l'ordre, la couverture, un intercalaire de couleur par gamme, une feuille par AMM puis
  le bilan (dossiers à retrouver, à scanner, corrigés, pas encore vérifiés, pages en trop). Une page pas
  encore vérifiée porte un cadre de constat à cocher à la main, pour vérifier aussi sur papier. Il faut
  compter environ 0,4 s pour les 207 pages de la Guinée.

## Ajouter une page, importer un scan depuis une page

- **Ajouter une page** (en haut du classeur, ou « Créer la page » sur une page en trop du bilan) : un dossier
  présent sur le papier mais oublié dans AMM GH.
  - L'AMM du produit est créée dans le pays du classeur. Le produit du catalogue est repris s'il existe, par
    son libellé, un alias ou la même clé de rapprochement ; sinon il est créé.
  - La page prend sa place alphabétique. Au siège, la gamme est celle du classeur, et un produit en « L »
    ajouté depuis Générale A-K va dans Générale L-Z. Le classeur s'ouvre sur la nouvelle page.
  - Une AMM qui existe déjà est refusée.
- **Importer le scan** (sur chaque page, ou glisser-déposer du fichier sur la feuille) : le scan est envoyé
  comme un import de dossier déjà rattaché à cette AMM. L'analyse ne cherche ni le produit ni le pays : elle
  lit le n° d'AMM et les dates, range le scan (origine ou renouvellement), corrige la fiche si la décision
  officielle le dit, puis la page se met à jour (miniature agrafée, dates, statut).
  - Le dossier importé reste visible dans « Import de dossiers AMM » avec son bilan.
  - S'il demande une vérification, la page donne le lien.
- **Détails réalistes** :
  - la pile de feuilles s'épaissit à droite au début du classeur et à gauche à mesure qu'on avance ;
  - le scan est agrafé à la fiche par un trombone ;
  - la note de l'archiviste apparaît en post-it jaune sur la page ;
  - un dossier complet est rangé dans sa pochette plastique (reflets), une AMM expirée est sur papier
    jauni au coin corné ;
  - un renouvellement déposé ou en instruction est tamponné « DÉPOSÉ le … », à l'écran comme dans le PDF ;
  - le bruit de page qui tourne est synthétisé dans le navigateur (bouton « Son », coupé par défaut) ;
  - chaque classeur porte le drapeau de son pays, dessiné en SVG pour s'afficher aussi sous Windows ;
  - un classeur ouvert par un archiviste est sorti de l'étagère avec un marque-page à son prénom. La
    page envoie un signal chaque minute (`POST /binders/{clé}/presence`, `DELETE` en sortant), et
    l'étagère se rafraîchit toutes les 30 s.

## Tout est relié : dashboard, imports Excel, imports de dossiers

- **Classeur toujours à jour** : les classeurs se recalculent depuis les AMM. Une fiche modifiée
  (dashboard, import Excel du Dashboard AMM Afrique, import de dossier) ou une AMM ajoutée apparaît
  sans recharger la page.
  - Un événement temps réel rafraîchit les classeurs (ou la relève périodique si le temps réel est
    coupé).
  - Un classeur ouvert intègre les pages ajoutées ou retirées en gardant la page en cours.
- **À revérifier** :
  - Le constat garde les valeurs vérifiées (n°, dates d'origine et du dernier renouvellement).
  - Si la fiche change ensuite, la page affiche « À revérifier » avec l'ancienne et la nouvelle valeur et
    l'origine du changement (import Excel du Dashboard, import de dossier ou modification de la fiche). Le
    tampon pâlit.
  - La page compte parmi « À vérifier ou revérifier ». La reprise, l'intercalaire, la page de garde et le
    PDF la signalent.
- **Provenance** : chaque page indique la ligne du Dashboard (feuille, n° de ligne, lien vers l'import
  Excel) et le dernier dossier importé (lien vers le dossier).
- **Depuis ailleurs vers le classeur** :
  - la fiche AMM et le dossier importé ont un bouton « Classeur … · page n/N », avec l'état du constat
    (vérifié, corrigé, absent, à vérifier, à revérifier) ; il ouvre le classeur directement sur la page
    (`/classeurs/{clé}?amm={id}`) ;
  - le Dashboard Afrique montre l'avancement des classeurs papier (pages vérifiées, corrigées, dossiers
    absents, décisions à scanner, pages en trop, classeurs ouverts en ce moment).

## Classeur complet avec les décisions officielles (siège)

Le bouton **Télécharger** (étagère, classeur ouvert, bilan) propose deux versions :

- **Fiches du classeur** : générées immédiatement.
- **Avec les décisions officielles** : chaque fiche est suivie des scans de la décision d'origine, puis de
  ses renouvellements (documents « AMM » en vigueur), dans l'ordre du classeur papier.
  - Une fiche porte la mention « N décisions jointes ».
  - Une AMM sans scan reste marquée « Aucun scan ».
  - Un scan illisible ou absent du stockage est remplacé par une page d'avertissement.

Déroulement :

- **Préparation** : elle tourne en arrière-plan (tâche Celery `build_binder_export`) et une seule à la fois
  par classeur. La fenêtre affiche l'avancement. Une notification prévient le demandeur quand c'est prêt.
- **Conservation** : seul le dernier classeur prêt est gardé dans le stockage (R2), car ces fichiers pèsent
  plusieurs dizaines de Mo.
- **Mémoire** : le service a 512 Mo. Les scans sont copiés sur disque un par un, puis assemblés par
  `qpdf`, qui ne les lit qu'au moment d'écrire. Mesure sur 207 décisions de 3,5 Mo (Guinée, 630 pages,
  723 Mo) : 118 Mo pour Python, 116 Mo pour qpdf, 6 s hors téléchargement depuis R2.
- **Reprise** : une préparation interrompue par un redémarrage est close par le rattrapage (35 min), puis on
  peut la relancer.

## API

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET | `/api/v1/binders` | étagère (classeurs visibles, avancement) |
| GET | `/api/v1/binders/{clé}` | classeur complet : intercalaires, pages (avec `changed_since_check`, `trace`), pages en trop, page de reprise |
| GET | `/api/v1/binders/locate?amm={id}` | classeur et page d'une AMM, état du constat |
| POST | `/api/v1/binders/{clé}/check` | constat `{amm, result, corrections[], note}` |
| POST | `/api/v1/binders/{clé}/uncheck` | annuler le constat `{amm}` |
| POST, DELETE | `/api/v1/binders/{clé}/extras[/{id}]` | pages en trop |
| POST | `/api/v1/binders/{clé}/pages` | ajouter la page d'un produit oublié `{product_name, range_code?, original_number?, original_start_date?, extra_id?}` |
| POST | `/api/v1/binders/{clé}/pages/{amm}/scan` | importer le scan d'une page (multipart `files`), lu comme un import de dossier |
| GET | `/api/v1/binders/{clé}/pdf` | PDF des fiches (siège uniquement) |
| GET, POST | `/api/v1/binders/{clé}/exports` | préparations avec décisions officielles ; POST en lance une (siège) |
| GET | `/api/v1/binders/{clé}/exports/{id}/file` | classeur complet prêt (siège) |

Exemples de clés : `SN-generale-a-k`, `SN-cardio`, `ML`, `CI`.
