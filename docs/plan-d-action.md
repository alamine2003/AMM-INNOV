# Plan d'action (1.2.6)

Menu **Plan d'action** (tous les rôles, limité aux pays de chacun), et carte sur les
Dashboards. But : agir vite sur les fiches incomplètes, sans comparer une AMM à une autre.

## Les manques

| Code (`?gap=`) | Libellé | Condition sur la fiche | Où agir |
| --- | --- | --- | --- |
| `no_original` | Origine non identifiée | n° ou date de début d'origine absents | onglet Détail |
| `missing_renewal` | Sans renouvellement | fin d'origine passée, aucun renouvellement obtenu ni en cours | onglet Renouvellements |
| `to_file` | Renouvellement à déposer | expirée ou à renouveler, rien en cours, hors cas précédent | onglet Renouvellements |
| `original_scan` | Décision d'origine sans scan | aucun scan AMM courant rattaché à l'origine | onglet Documents |
| `renewal_scan` | Renouvellement sans scan | un renouvellement obtenu sans scan AMM courant | onglet Documents |

Code : `apps/amm/services/gaps.py`. Les conditions sont des requêtes simples (pas de calcul de
chronologie) : le plan s'affiche vite même sur toutes les AMM.

## Ordre

`apps/amm/services/priority.py` : expirées, puis à renouveler, puis valides, puis échéance
inconnue ; à statut égal, l'échéance la plus proche. Le même ordre sert au rangement des
dossiers en attente (`apps/imports/hooks.py`, `by_regulatory_urgency`).

## API

- `GET /api/v1/amms/action-plan?country=SN&limit=8` : `total` (AMM avec au moins un manque) et,
  par manque, `count` et les `limit` premières AMM.
- `GET /api/v1/amms?gap=no_original,missing_renewal` : la liste complète (au moins un des
  manques), exportable en Excel comme toute la liste.

## Rangement : rangé, ou la raison est dite

Un dossier « prêt à ranger » porte toujours `status_reason` : l'erreur du dernier rangement
automatique (`filing_reason`, notée aussi dans le journal des erreurs sauf fiche changée
pendant l'analyse), rangement automatique désactivé, analyse à relire, ou « en file
d'attente ».
