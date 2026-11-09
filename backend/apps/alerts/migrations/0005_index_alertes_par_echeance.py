"""Alertes par statut et échéance (1.1.8)."""

from django.db import migrations, models

from apps.core.db import AddIndexOnline, trigram_index


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY ne tourne pas dans une transaction : l'application reste
    # utilisable pendant la création des index.
    atomic = False

    dependencies = [
        ("alerts", "0004_alert_resolutions"),
    ]

    operations = [
        AddIndexOnline(
            model_name="alert",
            index=models.Index(fields=["status", "due_date"], name="alert_status_due_idx"),
        ),
    ]
