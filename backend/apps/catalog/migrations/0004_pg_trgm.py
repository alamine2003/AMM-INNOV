"""Extension pg_trgm : index trigramme pour la recherche textuelle (1.1.8)."""

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_remove_country_filing_lead_months"),
    ]

    # Sans effet hors Postgres (SQLite en développement).
    operations = [TrigramExtension()]
