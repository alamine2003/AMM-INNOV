from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]

    operations = [
        migrations.AddConstraint(
            model_name="document",
            constraint=models.UniqueConstraint(
                condition=models.Q(("archived_at__isnull", True)),
                fields=("amm", "sha256"),
                name="doc_amm_sha256_active_uniq",
            ),
        ),
    ]
