# Audit, traçabilité et permissions (1.2.3)

## Permissions

Page **Administration › Permissions**, réservée au CEO. Un tableau rôles × actions.

| Rubrique | Action (`apps/accounts/roles.py`) | Par défaut |
|---|---|---|
| Classeurs | `binder.edit`, `binder.remove_passage`, `binder.rename_page`, `binder.delete_page`, `binder.remove_piece`, `binder.download` | CEO, siège |
| Référentiels | `catalog.manage` (pays, gammes, produits) | CEO, siège |
| Référentiels | `catalog.merge` (fusion de produits) | CEO |
| Documents | `documents.delete` (retirer un scan) | CEO, siège |
| Alertes | `alerts.manage_rules` | CEO, siège |
| Dépôts | `deposits.manage_pieces` | CEO, siège |
| Administration | `trash.restore`, `audit.view` | CEO, siège |
| Administration | `permissions.manage` | CEO, **ne se règle pas** |

Fonctionnement :

- `ACTION_ROLES` reste le réglage par défaut. Une case changée par le CEO crée une ligne
  `ActionGrant(action, rôle, autorisé)` ; sans ligne, le défaut s'applique. Une case remise à
  sa valeur actuelle n'écrit rien.
- `can(user, action)` lit les réglages du rôle une fois par requête : un changement
  s'applique dès la requête suivante de chacun. L'interface (`actions` de `/me`) se met à jour
  à la prochaine ouverture de l'application.
- Le CEO garde toujours tous les droits, et `permissions.manage` ne se règle pas : personne ne
  peut s'enfermer dehors. L'API refuse toute tentative (400).
- Le **périmètre pays** ne se règle pas ici : un utilisateur pays ne voit que ses pays. Un
  droit accordé à un rôle pays reste limité à ses pays (corbeille, audit).
- Restent fixes : gestion des comptes, imports Excel et synchronisation GHPL (siège et CEO),
  car ils touchent tous les pays.
- Chaque changement est gardé dans l'historique (`HistoricalActionGrant`) et apparaît dans
  l'audit.

Côté vues : `RolePermission` accepte `write_action`, `delete_action` et
`action_permissions` (réglables), en plus des `write_roles` historiques (fixes). En cas de
refus, le message de `MESSAGES` est renvoyé.

API : `GET /api/v1/permissions` (tableau), `PUT /api/v1/permissions`
`{"grants": [{"action", "role", "allowed"}]}`.

## Audit et traçabilité

Page **Administration › Audit** (droit `audit.view`, CEO et siège par défaut).

Rien n'est saisi pour l'audit : `apps/administration/audit.py` relit

- l'historique `simple_history` de chaque modèle suivi (découvert automatiquement) :
  créations et modifications, avec auteur, date, motif et champs changés (avant → après ; pour
  un lien, seul le nom du champ) ;
- la corbeille : mises à la corbeille (avec le nombre d'éléments liés) et restaurations ;
- l'historique des comptes (nouveau) : création, modification, désactivation, et connexions
  (`last_login`). Le mot de passe n'est jamais copié.

Les lignes « supprimé » de l'historique ne sont pas reprises : la corbeille les résume.

Filtres : personne, action (`created`, `updated`, `login`, `deleted`, `restored`), type
(`amm.MarketingAuthorization`…), pays (ISO2), période (`since`, `until`). Pages de 50
événements, 200 pages au plus ; chaque page lit au plus `page × 50` lignes par source.

API : `GET /api/v1/audit`, `GET /api/v1/audit/filters`.

## Retour arrière

1. D'abord, avec le code 1.2.3 encore en place : `python manage.py migrate accounts 0002`.
   Les tables `ActionGrant` et l'historique des comptes sont supprimés ; les droits reviennent
   aux défauts du code. Aucune autre donnée n'est touchée.
2. Ensuite, redéployer le tag `v1.2.2`.
