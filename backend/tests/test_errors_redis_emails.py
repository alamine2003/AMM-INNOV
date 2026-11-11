"""1.2.5 : journal des erreurs, surveillance de Redis, e-mails d'alerte coupés."""

from unittest import mock

import pytest
from django.test import override_settings

from apps.accounts.models import User
from apps.administration.tasks import watch_redis_memory
from apps.core import errors
from apps.core.models import ErrorEvent
from apps.core.redis_usage import check_redis_memory
from apps.notifications.models import Notification
from apps.notifications.tasks import send_weekly_digest

pytestmark = pytest.mark.django_db


# --- Journal des erreurs --------------------------------------------------------------------


def test_same_error_is_counted_not_duplicated_and_reopens():
    errors.record(source="server", kind="KeyError", message="'amm' 12", location="GET /amms")
    errors.record(source="server", kind="KeyError", message="'amm' 47", location="GET /amms")
    event = ErrorEvent.objects.get()
    assert event.count == 2
    event.resolved_at = event.last_seen
    event.save()
    errors.record(source="server", kind="KeyError", message="'amm' 99", location="GET /amms")
    event.refresh_from_db()
    assert event.count == 3 and event.resolved_at is None


def test_recording_never_raises():
    with mock.patch.object(ErrorEvent.objects, "filter", side_effect=RuntimeError("base")):
        errors.record(source="server", kind="X", message="y")  # aucune exception


def test_server_exception_is_journaled(client):
    from django.core.signals import got_request_exception

    try:
        raise ValueError("calcul impossible pour 3 AMM")
    except ValueError:
        got_request_exception.send(sender=None, request=None)
    event = ErrorEvent.objects.get()
    assert event.source == "server" and event.kind == "ValueError"
    assert "calcul impossible" in event.message and "Traceback" in event.detail


def test_interface_reports_errors_and_only_the_ceo_reads_them(
    ceo_client, hq_client, country_client
):
    payload = {"kind": "TypeError", "message": "x is undefined", "path": "/classeurs/SN"}
    assert country_client.post("/api/v1/client-errors", payload).status_code == 204
    assert ErrorEvent.objects.get().source == "interface"
    assert hq_client.get("/api/v1/errors").status_code == 403
    listed = ceo_client.get("/api/v1/errors?state=open").json()["results"]
    assert listed[0]["message"] == "x is undefined" and listed[0]["last_user"] == "Fatou"
    event_id = listed[0]["id"]
    assert ceo_client.post(f"/api/v1/errors/{event_id}/resolve").json()["resolved_by"]
    assert ceo_client.get("/api/v1/errors?state=open").json()["count"] == 0


# --- Redis ----------------------------------------------------------------------------------


@override_settings(REDIS_WARN_PCT=80)
def test_redis_nearly_full_warns_the_ceo_in_app_once_a_day(users):
    usage = {"used": 21 * 1024 * 1024, "limit": 25 * 1024 * 1024, "pct": 84.0}
    with mock.patch("apps.administration.tasks.redis_memory", return_value=usage):
        assert watch_redis_memory()["notified"] == 1
        assert watch_redis_memory()["notified"] == 0
    notification = Notification.objects.get(user=users["ceo"])
    assert notification.channel == Notification.Channel.IN_APP
    assert notification.title == "Redis presque plein : 84 %"
    assert not Notification.objects.filter(user=users["hq"]).exists()


def test_redis_integrity_check():
    usage = {"used": 24 * 1024 * 1024, "limit": 25 * 1024 * 1024, "pct": 96.0}
    with mock.patch("apps.core.redis_usage.redis_memory", return_value=usage):
        check = check_redis_memory(None)
    assert check.severity == "ERROR" and check.items
    with mock.patch("apps.core.redis_usage.redis_memory", return_value=None):
        assert not check_redis_memory(None).items


# --- E-mails coupés -------------------------------------------------------------------------


@override_settings(ALERT_EMAILS_ENABLED=False)
def test_no_alert_email_when_disabled(users, mailoutbox):
    from apps.notifications.reminders import reminder_channels

    with override_settings(RENEWAL_REMINDER_CHANNELS=["IN_APP", "EMAIL"]):
        assert reminder_channels() == ["IN_APP"]
    assert send_weekly_digest()["status"] == "disabled"
    assert mailoutbox == []
    assert User.objects.exists()
