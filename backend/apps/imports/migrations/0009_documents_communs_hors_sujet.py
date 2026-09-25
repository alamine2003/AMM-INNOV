"""Reprise unique : documents communs d'un dossier pays rangés dans des fiches hors sujet.

Les dossiers du Mali rangés le 25/09/2026 ont reçu dans chaque fiche les recueils de décisions
et les AMM de PALUCARE posés à la racine du dossier pays. Render gratuit n'offrant pas de
terminal, la reprise s'exécute au déploiement ; elle n'archive que ce que les règles actuelles
écartent (voir `apps.imports.dossier.cleanup`) et ne bloque jamais le démarrage.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def forward(apps, schema_editor):
    try:
        from apps.imports.dossier.cleanup import detach_unrelated_common_documents

        report = detach_unrelated_common_documents()
        if report["examined"]:
            logger.warning("Reprise des documents communs : %s", report)
    except Exception:  # la reprise se relance à la main : manage.py nettoyer_documents_communs
        logger.exception("Reprise des documents communs impossible")


class Migration(migrations.Migration):
    dependencies = [
        ("imports", "0008_dossier_attempts"),
        ("amm", "0004_workflow_amm_statuts"),
        ("catalog", "0003_remove_country_filing_lead_months"),
        ("documents", "0002_document_sha256_unique_active"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
