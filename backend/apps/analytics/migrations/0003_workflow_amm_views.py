"""Vues analytics alignées sur le workflow AMM (statut « À renouveler », dépôt idéal, limite
agence ; plus de statut « En cours d'instruction »).

`v_amm_current` et `mv_country_kpi` changent de colonnes : elles sont supprimées puis recréées
(CREATE OR REPLACE ne sait pas renommer une colonne). Les droits de grafana_ro suivent par les
privilèges par défaut du schéma `analytics` (0001).
"""

from django.db import migrations

from apps.analytics.migrations._sql_0001 import MV_COUNTRY_KPI as OLD_MV_COUNTRY_KPI
from apps.analytics.migrations._sql_0001 import V_DATA_QUALITY as OLD_V_DATA_QUALITY
from apps.analytics.sql import MV_COUNTRY_KPI, V_AMM_CURRENT, V_DATA_QUALITY

# Ancienne vue, relue sur la colonne renommée (le retour arrière de amm 0004 suit celui-ci).
OLD_V_AMM_CURRENT_ON_RENAMED_COLUMN = """
CREATE OR REPLACE VIEW analytics.v_amm_current AS
SELECT a.id AS amm_id,
       c.iso2 AS country_iso2,
       c.name AS country_name,
       r.code AS range_code,
       p.name AS product_name,
       a.original_number,
       a.status,
       a.urgency,
       a.effective_end_date,
       a.agency_filing_deadline AS filing_deadline,
       a.dossier_state,
       (a.effective_end_date - CURRENT_DATE) AS days_remaining,
       EXISTS (
           SELECT 1 FROM documents_document d
           WHERE d.amm_id = a.id AND d.kind = 'AMM' AND d.is_current AND d.archived_at IS NULL
       ) AS has_current_scan
FROM amm_marketingauthorization a
JOIN catalog_country c ON c.id = a.country_id
JOIN catalog_product p ON p.id = a.product_id
LEFT JOIN catalog_productrange r ON r.id = p.range_id;
"""

DROP = [
    "DROP VIEW IF EXISTS analytics.v_amm_current;",
    "DROP MATERIALIZED VIEW IF EXISTS analytics.mv_country_kpi;",
]


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for statement in [*DROP, V_AMM_CURRENT, MV_COUNTRY_KPI, V_DATA_QUALITY]:
        schema_editor.execute(statement)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for statement in [
        *DROP,
        OLD_V_AMM_CURRENT_ON_RENAMED_COLUMN,
        OLD_MV_COUNTRY_KPI,
        OLD_V_DATA_QUALITY,
    ]:
        schema_editor.execute(statement)


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0002_ops_backlog_view"),
        ("amm", "0004_workflow_amm_statuts"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
