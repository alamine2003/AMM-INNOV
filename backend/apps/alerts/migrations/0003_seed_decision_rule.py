"""Seeds the global DECISION rule (PRD 6.4), missing from the initial seed."""

from django.db import migrations

from apps.alerts.defaults import DEFAULT_RULES


def forwards(apps, schema_editor):
    AlertRule = apps.get_model("alerts", "AlertRule")
    for spec in DEFAULT_RULES:
        if spec["code"] == "DECISION":
            AlertRule.objects.get_or_create(code=spec["code"], country=None, defaults=spec)


def backwards(apps, schema_editor):
    AlertRule = apps.get_model("alerts", "AlertRule")
    AlertRule.objects.filter(country=None, code="DECISION").delete()


class Migration(migrations.Migration):
    dependencies = [("alerts", "0002_seed_default_rules")]
    operations = [migrations.RunPython(forwards, backwards)]
