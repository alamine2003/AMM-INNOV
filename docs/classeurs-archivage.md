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

## API

| Méthode | Chemin | Rôle |
| --- | --- | --- |
| GET | `/api/v1/binders` | étagère (classeurs visibles, avancement) |
| GET | `/api/v1/binders/{clé}` | classeur complet : intercalaires, pages, pages en trop, page de reprise |
| POST | `/api/v1/binders/{clé}/check` | constat `{amm, result, corrections[], note}` |
| POST | `/api/v1/binders/{clé}/uncheck` | annuler le constat `{amm}` |
| POST, DELETE | `/api/v1/binders/{clé}/extras[/{id}]` | pages en trop |
| GET | `/api/v1/binders/{clé}/pdf` | PDF du classeur (siège uniquement) |

Exemples de clés : `SN-generale-a-k`, `SN-cardio`, `ML`, `CI`.
