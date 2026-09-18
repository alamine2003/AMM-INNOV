"""Non-régression de la campagne de chaos : récupération des tâches (s12, s13, H10-H12).

Le principe retenu : la base est la source de vérité de « ce qui reste à faire ». Une tâche
perdue (Redis coupé à la publication, worker tué, API Gmail en panne plus longtemps que les
relances) est retrouvée par `recover_pending_work` et republiée, sans doublon.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.imports.models import DossierImport
from apps.notifications.models import Notification


@pytest.fixture
def email(users):
    def _make(age_minutes=30, **kwargs):
        notification = Notification.objects.create(
            user=users["ceo"], channel=Notification.Channel.EMAIL, title="J-30", body="…", **kwargs
        )
        Notification.objects.filter(pk=notification.pk).update(
            created_at=timezone.now() - timedelta(minutes=age_minutes)
        )
        notification.refresh_from_db()
        return notification

    return _make


# --- e-mails ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_failed_send_is_recorded_on_the_notification(email):
    from celery.exceptions import Retry

    from apps.notifications.tasks import send_alert_email

    notification = email()
    with mock.patch(
        "apps.notifications.tasks.send_alert_message", side_effect=ConnectionError("Gmail 500")
    ), pytest.raises((ConnectionError, Retry)):  # la tâche demande une relance
        send_alert_email.apply(args=[str(notification.pk)], throw=True)
    notification.refresh_from_db()
    assert notification.sent_at is None
    assert notification.send_attempts >= 1
    assert "Gmail 500" in notification.last_error
    assert notification.last_attempt_at is not None


@pytest.mark.django_db
def test_email_retries_span_a_long_outage():
    """3 relances en ~7 s ne couvraient pas une panne de 3 minutes (s13 outage_3min)."""
    from apps.notifications.tasks import send_alert_email

    backoff = send_alert_email.retry_backoff
    retries = send_alert_email.max_retries
    horizon = sum(min(backoff * 2**i, send_alert_email.retry_backoff_max) for i in range(retries))
    assert horizon >= 10 * 60
    # une relance plus longue que visibility_timeout serait redistribuée : doublons
    assert send_alert_email.retry_backoff_max < 3600


@pytest.mark.django_db
def test_sweeper_republishes_lost_emails_once(email):
    from apps.core.tasks import recover_pending_work

    lost = email(age_minutes=30)
    fresh = email(age_minutes=0)  # sa tâche Celery est peut-être encore en file
    sent = email(age_minutes=30, sent_at=timezone.now())
    exhausted = email(age_minutes=30, send_attempts=60)
    with mock.patch("apps.notifications.tasks.send_alert_email.delay") as delay:
        report = recover_pending_work()
    delay.assert_called_once_with(str(lost.pk))
    assert report["emails"] == 1
    assert {fresh.pk, sent.pk, exhausted.pk}.isdisjoint({c.args[0] for c in delay.call_args_list})


@pytest.mark.django_db
def test_retried_email_keeps_the_same_message_id(email):
    """Réponse de Google perdue après l'envoi : la relance porte le même Message-ID."""
    from django.core import mail

    from apps.notifications.tasks import send_alert_message

    notification = email()
    send_alert_message(notification, "corps")
    send_alert_message(notification, "corps")
    ids = {message.extra_headers["Message-ID"] for message in mail.outbox}
    assert ids == {f"<notification-{notification.pk}@amm.local>"}


@pytest.mark.django_db
def test_unreadable_pdf_is_not_retried_forever(make_amm, make_scan):
    """Un PDF invalide ne doit pas revenir dans le rattrapage toutes les 5 minutes."""
    from apps.core.tasks import recover_pending_work
    from apps.documents.models import Document
    from apps.documents.tasks import generate_document_preview

    document = make_scan(make_amm())
    Document.objects.filter(pk=document.pk).update(
        page_count=None, uploaded_at=timezone.now() - timedelta(minutes=30)
    )
    with mock.patch("pypdf.PdfReader", side_effect=ValueError("structure invalide")):
        assert generate_document_preview(str(document.pk))["status"] == "unreadable"
    document.refresh_from_db()
    assert document.page_count == 0
    with mock.patch("apps.documents.tasks.generate_document_preview.delay") as delay:
        recover_pending_work()
    delay.assert_not_called()


@pytest.mark.django_db
def test_preview_redelivered_after_a_crash_is_not_rerun(make_amm, make_scan):
    """Un PDF qui tue le worker ne doit pas être réanalysé à chaque redistribution."""
    from apps.documents.models import Document
    from apps.documents.tasks import generate_document_preview

    document = make_scan(make_amm())
    Document.objects.filter(pk=document.pk).update(page_count=None)
    # la mort du processus (OOM = SIGKILL) ne passe par aucun except : BaseException la simule
    with mock.patch("pypdf.PdfReader", side_effect=SystemExit):
        with pytest.raises(SystemExit):
            generate_document_preview(str(document.pk))
    with mock.patch("pypdf.PdfReader") as reader:
        assert generate_document_preview(str(document.pk))["status"] == "already-done"
    reader.assert_not_called()


@pytest.mark.django_db
def test_sweeper_republishes_pending_import(users):
    from apps.core.tasks import recover_pending_work
    from apps.imports.models import ImportBatch

    batch = ImportBatch.objects.create(file="imports/x.xlsx", created_by=users["ceo"])
    long_ago = timezone.now() - timedelta(minutes=20)
    ImportBatch.objects.filter(pk=batch.pk).update(created_at=long_ago)
    with mock.patch("apps.imports.tasks.run_import.delay") as delay:
        recover_pending_work()
    delay.assert_called_once_with(str(batch.pk))


# --- analyses de dossier ------------------------------------------------------------------


@pytest.mark.django_db
def test_sweeper_frees_a_dossier_stuck_in_running(users):
    """Worker tué pendant l'analyse : le dossier restait RUNNING à vie et la relance était
    refusée (s12b)."""
    from apps.core.tasks import recover_pending_work

    stuck = DossierImport.objects.create(
        root_name="d", created_by=users["ceo"], status=DossierImport.Status.RUNNING,
        started_at=timezone.now() - timedelta(minutes=40),
    )
    running = DossierImport.objects.create(
        root_name="e", created_by=users["ceo"], status=DossierImport.Status.RUNNING,
        started_at=timezone.now() - timedelta(minutes=2),
    )
    recover_pending_work()
    stuck.refresh_from_db()
    running.refresh_from_db()
    assert stuck.status == DossierImport.Status.FAILED and "interrompue" in stuck.error
    assert running.status == DossierImport.Status.RUNNING


@pytest.mark.django_db
def test_sweeper_republishes_pending_dossier(users):
    from apps.core.tasks import recover_pending_work

    pending = DossierImport.objects.create(
        root_name="d", created_by=users["ceo"], status=DossierImport.Status.PENDING
    )
    twenty_minutes_ago = timezone.now() - timedelta(minutes=20)
    DossierImport.objects.filter(pk=pending.pk).update(created_at=twenty_minutes_ago)
    with mock.patch("apps.imports.tasks.analyze_dossier.delay") as delay:
        recover_pending_work()
    delay.assert_called_once_with(str(pending.pk))


@pytest.mark.django_db
def test_analysis_claim_records_start_time(users):
    from apps.imports.tasks import analyze_dossier

    batch = DossierImport.objects.create(root_name="d", created_by=users["ceo"])
    with mock.patch("apps.imports.dossier.preview.build_preview", side_effect=ValueError):
        analyze_dossier(str(batch.pk))
    batch.refresh_from_db()
    assert batch.started_at is not None


# --- alertes : jamais d'alerte créée sans sa notification --------------------------------


@pytest.mark.django_db
def test_alert_creation_and_dispatch_are_atomic(rules, users, make_amm, fixed_today):
    from apps.alerts.models import Alert
    from apps.alerts.services.engine import evaluate_rules

    make_amm(start=fixed_today - timedelta(days=365 * 5 - 20))  # J-30 franchi, pays SN
    with mock.patch(
        "apps.notifications.services.dispatch", side_effect=RuntimeError("crash du worker")
    ), pytest.raises(RuntimeError):
        evaluate_rules(today=fixed_today)
    assert Alert.objects.count() == 0  # annulée avec sa notification
    report = evaluate_rules(today=fixed_today)
    assert report["created"] > 0 and report["notified"] > 0
    # les alertes récentes sont notifiées ; les anciennes restent silencieuses par conception
    recent = [a for a in Alert.objects.all() if (fixed_today - a.due_date).days <= 30]
    assert recent and all(alert.notifications.exists() for alert in recent)


# --- digest hebdomadaire ------------------------------------------------------------------


@pytest.mark.django_db
def test_weekly_digest_survives_one_failure_and_is_not_resent(rules, users, make_amm, fixed_today):
    from apps.notifications import tasks

    make_amm(start=fixed_today - timedelta(days=365 * 5 - 20))
    calls = []

    def flaky(subject, message, from_email, recipient_list):
        calls.append(recipient_list[0])
        if recipient_list[0] == "hq@test.local" and calls.count("hq@test.local") == 1:
            raise ConnectionError("Gmail 500")

    with mock.patch.object(tasks, "send_mail", side_effect=flaky):
        first = tasks.send_weekly_digest(today=fixed_today.isoformat())
        second = tasks.send_weekly_digest(today=fixed_today.isoformat())
    assert first["failed"] == 1 and first["sent"] >= 1
    assert second["sent"] == 1  # seul l'utilisateur en échec est servi à nouveau
    assert calls.count("ceo@test.local") == 1
