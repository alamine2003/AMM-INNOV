# Corbeille

Depuis la 1.2.2, rien n'est effacé dans AMM GH. Ce qu'une personne supprime part à la corbeille
(Administration > Corbeille, CEO et siège), avec tout ce qui partait avec lui, et peut être
restauré à l'identique, avec les mêmes identifiants. La corbeille n'est jamais vidée.

## Ce qui va à la corbeille

| Suppression | Ce qui part avec |
| --- | --- |
| Fiche AMM (API), page du classeur | renouvellements, documents (scans, pièces), alertes, rappels, vérification du classeur, imports de dossiers liés |
| Passage du classeur, renouvellement annulé | le renouvellement (ses pièces restent sur la fiche) |
| Page en trop | la page en trop |
| Pièce ou échantillon d'un dossier de dépôt | la ligne ; le fichier reste au stockage |
| Pays, gamme, produit, règle d'alerte, type de pièce | la ligne ; refusé s'il est encore utilisé |

Un compte utilisateur n'est pas supprimé : il est désactivé.

## Comment ça marche

`apps/core/trash.py` :

- `move_to_trash(obj, user=…)` rassemble ce que la suppression emporterait (lignes en cascade)
  et ce qu'elle modifierait (liens mis à vide), copie tout dans une `TrashEntry`, puis supprime
  comme avant ;
- `restore(entry, user=…)` remet les lignes et les liens, puis appelle les apps
  (`TRASH_RESTORED`) : l'AMM est recalculée (ordre des renouvellements, échéance, statut, ligne
  d'historique « restauré depuis la corbeille »), et une page du classeur est de nouveau suivie
  par les imports ;
- une restauration est refusée si un élément équivalent existe déjà (par exemple la même AMM
  recréée depuis) : il faut d'abord le supprimer ou le fusionner ;
- les vues DRF qui suppriment utilisent `TrashDestroyMixin`.

API : `GET /api/v1/trash?state=deleted|restored`, `POST /api/v1/trash/<id>/restore` (droit
`trash.restore`). Supprimer une page du classeur renvoie l'en-tête `X-Trash-Entry`, utilisé par
« Annuler ».

Ne restent effacés que des éléments techniques sans valeur d'archive : signal « classeur
ouvert », journaux de synchronisation de plus de 120 jours, notifications lues anciennes.
