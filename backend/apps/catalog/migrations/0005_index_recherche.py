"""Recherche par nom de produit et par libellé (alias) : index trigramme (1.1.8)."""

from django.db import migrations

from apps.core.db import AddIndexOnline, trigram_index


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY ne tourne pas dans une transaction : l'application reste
    # utilisable pendant la création des index.
    atomic = False

    dependencies = [
        ("catalog", "0004_pg_trgm"),
    ]

    operations = [
        AddIndexOnline(model_name="product", index=trigram_index("name", "product_name_trgm")),
        AddIndexOnline(model_name="productalias", index=trigram_index("raw_name", "alias_raw_name_trgm")),
    ]
