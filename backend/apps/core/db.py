"""Index de la base : recherche textuelle et création sans blocage.

Les recherches de l'API (`?search=`) passent par `icontains`, que Postgres écrit
`UPPER(col::text) LIKE UPPER('%…%')`. Un index B-tree ne sert pas ce `LIKE` à joker en tête :
il faut un index GIN trigramme (`pg_trgm`) sur la même expression `UPPER(col)`.
"""

from __future__ import annotations

from django.contrib.postgres.indexes import GinIndex, OpClass, PostgresIndex
from django.contrib.postgres.operations import AddIndexConcurrently, RemoveIndexConcurrently
from django.db.migrations.operations import AddIndex
from django.db.models.functions import Upper


def trigram_index(field: str, name: str) -> GinIndex:
    """Index servant `<field>__icontains` (recherche de l'API) sous Postgres."""
    return GinIndex(OpClass(Upper(field), name="gin_trgm_ops"), name=name)


class AddIndexOnline(AddIndex):
    """`AddIndex` qui ne bloque pas l'application pendant sa création.

    - Postgres : `CREATE INDEX CONCURRENTLY` (la migration doit être `atomic = False`) ;
    - autre base (SQLite en développement) : index ordinaire, et les index propres à Postgres
      (GIN trigramme) sont ignorés.

    L'état des modèles est celui d'`AddIndex` : `makemigrations --check` reste juste.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "postgresql":
            AddIndexConcurrently(self.model_name, self.index).database_forwards(
                app_label, schema_editor, from_state, to_state
            )
        elif not isinstance(self.index, PostgresIndex):
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor == "postgresql":
            RemoveIndexConcurrently(self.model_name, self.index.name).database_forwards(
                app_label, schema_editor, from_state, to_state
            )
        elif not isinstance(self.index, PostgresIndex):
            super().database_backwards(app_label, schema_editor, from_state, to_state)


__all__ = ["AddIndexOnline", "trigram_index"]
