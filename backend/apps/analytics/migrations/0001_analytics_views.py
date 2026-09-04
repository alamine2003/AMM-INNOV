"""Creates the `analytics` schema, its views and the `grafana_ro` role (PostgreSQL only)."""

import os

from django.db import migrations

from apps.analytics.sql import BACKWARD_STATEMENTS, FORWARD_STATEMENTS, grafana_role_sql


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for statement in FORWARD_STATEMENTS:
        schema_editor.execute(statement)
    schema_editor.execute(grafana_role_sql(os.environ.get("GRAFANA_DB_PASSWORD", "grafana_ro")))


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for statement in BACKWARD_STATEMENTS:
        schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_initial"),
        ("catalog", "0001_initial"),
        ("amm", "0001_initial"),
        ("documents", "0001_initial"),
        ("alerts", "0001_initial"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
