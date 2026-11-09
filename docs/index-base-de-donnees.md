# Index de la base de données

Depuis la 1.1.8, AMM GH porte des index pour ses requêtes les plus fréquentes. Ils ne changent ni
l'API ni les écrans : seule la vitesse change. Le détail des choix est dans la revue
d'architecture du 09/11/2026.

## Recherche textuelle

La recherche des listes (`?search=`) utilise `icontains`, que Postgres écrit
`UPPER(col::text) LIKE UPPER('%texte%')`. Un index B-tree ordinaire ne sert pas un `LIKE` qui
commence par un joker. Ces colonnes ont donc un index GIN trigramme (extension `pg_trgm`) sur
l'expression `UPPER(col)` :

| Index | Table | Colonne |
| --- | --- | --- |
| `product_name_trgm` | `catalog_product` | `name` |
| `alias_raw_name_trgm` | `catalog_productalias` | `raw_name` |
| `amm_number_trgm` | `amm_marketingauthorization` | `original_number` |
| `renewal_number_trgm` | `amm_renewal` | `number` |

Pour en ajouter un : `trigram_index("<colonne>", "<nom>")` (`apps/core/db.py`) dans
`Meta.indexes` du modèle. L'app `django.contrib.postgres` doit rester dans `INSTALLED_APPS` :
sans elle, Django écrit mal la classe d'opérateurs (`gin_trgm_ops`).

## Autres index

| Index | Table | Requête servie |
| --- | --- | --- |
| `doc_current_scan_idx` | `documents_document` | scan en vigueur d'une AMM (`amm`, `kind`, version courante non archivée) |
| `renewal_workflow_idx` | `amm_renewal` | renouvellements par étape (rappels, registre, dépôts) |
| `alert_status_due_idx` | `alerts_alert` | alertes ouvertes triées par échéance |
| `notif_user_recent_idx` | `notifications_notification` | notifications d'un utilisateur, récentes d'abord |
| `notif_user_unread_idx` | `notifications_notification` | notifications non lues d'un utilisateur |

## Création sans blocage

Les migrations utilisent `AddIndexOnline` (`apps/core/db.py`), avec `atomic = False` :

- sous Postgres, `CREATE INDEX CONCURRENTLY` : l'application reste utilisable pendant la
  création ;
- sous SQLite (développement), un index ordinaire, et les index propres à Postgres sont ignorés.

Retour arrière : `python manage.py migrate <app> <migration précédente>` supprime les index
(`DROP INDEX CONCURRENTLY`), sans toucher aux données.

## Vérification

`tests/test_db_indexes.py` vérifie que chaque index existe et que Postgres peut l'utiliser pour
sa requête (`EXPLAIN`, lectures séquentielles désactivées : les tables de test sont trop petites
pour que Postgres choisisse un index de lui-même).
