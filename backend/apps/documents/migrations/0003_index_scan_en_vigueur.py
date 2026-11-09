"""Scan en vigueur d'une AMM : index partiel (1.1.8)."""

from django.db import migrations, models

from apps.core.db import AddIndexOnline, trigram_index


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY ne tourne pas dans une transaction : l'application reste
    # utilisable pendant la création des index.
    atomic = False

    dependencies = [
        ("documents", "0002_document_sha256_unique_active"),
    ]

    operations = [
        AddIndexOnline(
            model_name="document",
            index=models.Index(
                fields=["amm", "kind"],
                condition=models.Q(is_current=True, archived_at__isnull=True),
                name="doc_current_scan_idx",
            ),
        ),
    ]
