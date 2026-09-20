"""Vue d'exploitation pour l'alerting Grafana (campagne de chaos, phase 4).

Grafana Cloud lit déjà la base : cette vue rend visibles les pannes silencieuses mesurées en
laboratoire (e-mails jamais partis, analyses bloquées, worker ou beat arrêté). Règles d'alerte
suggérées : emails_en_retard > 0 pendant 30 min, analyses_bloquees > 0, et
`now() - dernier_rattrapage > 15 min` (le rattrapage tourne toutes les 5 min : s'il vieillit,
le worker et beat sont arrêtés). Lecture accordée à grafana_ro par les privilèges par défaut du
schéma `analytics` (0001).
"""

from django.db import migrations

V_OPS_BACKLOG = """
CREATE OR REPLACE VIEW analytics.v_ops_backlog AS
SELECT
    (SELECT count(*) FROM notifications_notification
      WHERE channel = 'EMAIL' AND sent_at IS NULL
        AND created_at < now() - interval '30 minutes') AS emails_en_retard,
    (SELECT count(*) FROM notifications_notification
      WHERE channel = 'EMAIL' AND sent_at IS NULL AND send_attempts >= 60) AS emails_abandonnes,
    (SELECT count(*) FROM imports_dossierimport
      WHERE status IN ('PENDING', 'RUNNING')
        AND created_at < now() - interval '30 minutes') AS analyses_bloquees,
    (SELECT count(*) FROM imports_importbatch
      WHERE status IN ('PENDING', 'RUNNING')
        AND created_at < now() - interval '30 minutes') AS imports_bloques,
    (SELECT count(*) FROM documents_document
      WHERE page_count IS NULL AND content_type = 'application/pdf' AND archived_at IS NULL
        AND uploaded_at < now() - interval '1 hour') AS apercus_manquants,
    (SELECT max(last_run_at) FROM django_celery_beat_periodictask
      WHERE task = 'apps.core.tasks.recover_pending_work') AS dernier_rattrapage,
    now() AS mesure_le;
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(V_OPS_BACKLOG)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP VIEW IF EXISTS analytics.v_ops_backlog;")


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0001_analytics_views"),
        ("notifications", "0002_resilience_tracking"),
        ("imports", "0004_resilience_tracking"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
