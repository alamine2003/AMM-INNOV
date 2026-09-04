"""SQL of the `analytics` schema (PostgreSQL only): views for Grafana and the read-only role."""

CREATE_SCHEMA = "CREATE SCHEMA IF NOT EXISTS analytics;"

V_AMM_CURRENT = """
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
       a.filing_deadline,
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

MV_COUNTRY_KPI = """
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_country_kpi AS
SELECT c.iso2 AS country_iso2,
       c.name AS country_name,
       COUNT(a.id) AS total,
       COUNT(a.id) FILTER (WHERE a.status = 'VALIDE') AS valid,
       COUNT(a.id) FILTER (WHERE a.status = 'EXPIRE') AS expired,
       COUNT(a.id) FILTER (WHERE a.status = 'IN_PROCESS') AS in_process,
       COUNT(a.id) FILTER (WHERE a.status = 'INDETERMINE') AS undetermined,
       CASE WHEN COUNT(a.id) = 0 THEN 0
            ELSE ROUND(100.0 * COUNT(a.id) FILTER (WHERE a.status = 'VALIDE') / COUNT(a.id), 1)
       END AS pct_valid,
       COUNT(a.id) FILTER (
           WHERE a.status = 'VALIDE'
             AND a.effective_end_date <= CURRENT_DATE + INTERVAL '6 months'
       ) AS expiring_6m,
       COUNT(a.id) FILTER (
           WHERE a.status = 'VALIDE'
             AND a.effective_end_date <= CURRENT_DATE + INTERVAL '12 months'
       ) AS expiring_12m,
       CASE WHEN COUNT(a.id) = 0 THEN 0
            ELSE ROUND(
                100.0 * COUNT(a.id) FILTER (WHERE a.dossier_state = 'COMPLET') / COUNT(a.id), 1
            )
       END AS pct_complete
FROM catalog_country c
LEFT JOIN amm_marketingauthorization a ON a.country_id = c.id
GROUP BY c.iso2, c.name
WITH DATA;
CREATE UNIQUE INDEX IF NOT EXISTS mv_country_kpi_country_iso2_idx
    ON analytics.mv_country_kpi (country_iso2);
"""

MV_EXPIRY_PIPELINE = """
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.mv_expiry_pipeline AS
SELECT c.iso2 AS country_iso2,
       date_trunc('month', a.effective_end_date)::date AS month,
       COUNT(*) AS count
FROM amm_marketingauthorization a
JOIN catalog_country c ON c.id = a.country_id
WHERE a.effective_end_date IS NOT NULL
  AND a.effective_end_date >= date_trunc('month', CURRENT_DATE)
  AND a.effective_end_date < date_trunc('month', CURRENT_DATE) + INTERVAL '36 months'
GROUP BY c.iso2, date_trunc('month', a.effective_end_date)
WITH DATA;
CREATE UNIQUE INDEX IF NOT EXISTS mv_expiry_pipeline_country_month_idx
    ON analytics.mv_expiry_pipeline (country_iso2, month);
"""

V_ALERT_OPEN = """
CREATE OR REPLACE VIEW analytics.v_alert_open AS
SELECT al.id AS alert_id,
       c.iso2 AS country_iso2,
       p.name AS product_name,
       r.code AS rule_code,
       r.severity,
       al.due_date,
       al.status,
       u.email AS assigned_to_email,
       (CURRENT_DATE - al.triggered_at::date) AS age_days
FROM alerts_alert al
JOIN alerts_alertrule r ON r.id = al.rule_id
JOIN amm_marketingauthorization a ON a.id = al.amm_id
JOIN catalog_country c ON c.id = a.country_id
JOIN catalog_product p ON p.id = a.product_id
LEFT JOIN accounts_user u ON u.id = al.assigned_to_id
WHERE al.status IN ('OPEN', 'ACKNOWLEDGED');
"""

V_RENEWAL_FUNNEL = """
CREATE OR REPLACE VIEW analytics.v_renewal_funnel AS
SELECT c.iso2 AS country_iso2,
       rn.workflow_status,
       COUNT(*) AS count,
       AVG(rn.decision_date - rn.filing_date) FILTER (
           WHERE rn.decision_date IS NOT NULL AND rn.filing_date IS NOT NULL
       ) AS avg_days_to_decision
FROM amm_renewal rn
JOIN amm_marketingauthorization a ON a.id = rn.amm_id
JOIN catalog_country c ON c.id = a.country_id
GROUP BY c.iso2, rn.workflow_status;
"""

V_DATA_QUALITY = """
CREATE OR REPLACE VIEW analytics.v_data_quality AS
SELECT c.iso2 AS country_iso2,
       COUNT(a.id) FILTER (WHERE a.status = 'INDETERMINE') AS undetermined,
       COUNT(a.id) FILTER (WHERE a.dossier_state = 'INCOMPLET') AS incomplete,
       COUNT(a.id) FILTER (
           WHERE a.status = 'VALIDE' AND NOT EXISTS (
               SELECT 1 FROM documents_document d
               WHERE d.amm_id = a.id AND d.kind = 'AMM' AND d.is_current AND d.archived_at IS NULL
           )
       ) AS missing_scan
FROM catalog_country c
LEFT JOIN amm_marketingauthorization a ON a.country_id = c.id
GROUP BY c.iso2;
"""


def grafana_role_sql(password: str) -> str:
    escaped = password.replace("'", "''")
    return f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        BEGIN
            EXECUTE 'CREATE ROLE grafana_ro LOGIN PASSWORD ''{escaped}''';
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'Privilèges insuffisants pour créer le rôle grafana_ro.';
        END;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
        BEGIN
            EXECUTE 'GRANT USAGE ON SCHEMA analytics TO grafana_ro';
            EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO grafana_ro';
            EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA analytics '
                    'GRANT SELECT ON TABLES TO grafana_ro';
        EXCEPTION WHEN insufficient_privilege THEN
            RAISE NOTICE 'Privilèges insuffisants pour accorder les droits à grafana_ro.';
        END;
    END IF;
END
$$;
"""


FORWARD_STATEMENTS = [
    CREATE_SCHEMA,
    V_AMM_CURRENT,
    MV_COUNTRY_KPI,
    MV_EXPIRY_PIPELINE,
    V_ALERT_OPEN,
    V_RENEWAL_FUNNEL,
    V_DATA_QUALITY,
]

BACKWARD_STATEMENTS = [
    "DROP VIEW IF EXISTS analytics.v_data_quality;",
    "DROP VIEW IF EXISTS analytics.v_renewal_funnel;",
    "DROP VIEW IF EXISTS analytics.v_alert_open;",
    "DROP MATERIALIZED VIEW IF EXISTS analytics.mv_expiry_pipeline;",
    "DROP MATERIALIZED VIEW IF EXISTS analytics.mv_country_kpi;",
    "DROP VIEW IF EXISTS analytics.v_amm_current;",
    "DROP SCHEMA IF EXISTS analytics;",
]
