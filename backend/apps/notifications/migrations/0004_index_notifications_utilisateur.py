"""Notifications d'un utilisateur : récentes et non lues (1.1.8)."""

from django.db import migrations, models

from apps.core.db import AddIndexOnline, trigram_index


class Migration(migrations.Migration):
    # CREATE INDEX CONCURRENTLY ne tourne pas dans une transaction : l'application reste
    # utilisable pendant la création des index.
    atomic = False

    dependencies = [
        ("notifications", "0003_renewal_reminder"),
    ]

    operations = [
        AddIndexOnline(
            model_name="notification",
            index=models.Index(fields=["user", "-created_at"], name="notif_user_recent_idx"),
        ),
        AddIndexOnline(
            model_name="notification",
            index=models.Index(
                fields=["user"],
                condition=models.Q(read_at__isnull=True),
                name="notif_user_unread_idx",
            ),
        ),
    ]
