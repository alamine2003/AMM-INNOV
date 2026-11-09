"""Recherche par n° d'AMM et de renouvellement, renouvellements par étape (1.1.8)."""

from django.db import migrations, models

from apps.core.db import AddIndexOnline, trigram_index


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY ne tourne pas dans une transaction : l'application reste
    # utilisable pendant la création des index.
    atomic = False

    dependencies = [
        ("amm", "0004_workflow_amm_statuts"),
        ("catalog", "0004_pg_trgm"),
    ]

    operations = [
        AddIndexOnline(model_name="marketingauthorization", index=trigram_index("original_number", "amm_number_trgm")),
        AddIndexOnline(model_name="renewal", index=models.Index(fields=["workflow_status"], name="renewal_workflow_idx")),
        AddIndexOnline(model_name="renewal", index=trigram_index("number", "renewal_number_trgm")),
    ]
