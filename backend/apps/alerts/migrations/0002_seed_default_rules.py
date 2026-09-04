"""Seeds the global default alert rules (J-365, J-180, J-90, J-30, J0, DOSSIER)."""

from django.db import migrations

from apps.alerts.defaults import DEFAULT_RULES


def forwards(apps, schema_editor):
    AlertRule = apps.get_model("alerts", "AlertRule")
    for spec in DEFAULT_RULES:
        AlertRule.objects.get_or_create(code=spec["code"], country=None, defaults=spec)


def backwards(apps, schema_editor):
    AlertRule = apps.get_model("alerts", "AlertRule")
    AlertRule.objects.filter(country=None, code__in=[s["code"] for s in DEFAULT_RULES]).delete()


class Migration(migrations.Migration):
    dependencies = [("alerts", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
