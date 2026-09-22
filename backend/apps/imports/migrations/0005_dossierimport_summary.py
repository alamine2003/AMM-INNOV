from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("imports", "0004_resilience_tracking"),
    ]

    operations = [
        migrations.AddField(
            model_name="dossierimport",
            name="summary",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
