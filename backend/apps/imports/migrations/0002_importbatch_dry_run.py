from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("imports", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="importbatch",
            name="dry_run",
            field=models.BooleanField(default=False, verbose_name="simulation"),
        ),
    ]
