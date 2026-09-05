from datetime import timedelta

import pytest

from apps.alerts.models import Alert
from apps.alerts.services.engine import evaluate_rules
from apps.notifications.models import Notification
from tests.conftest import TODAY

pytestmark = pytest.mark.django_db


@pytest.fixture
def open_alerts(make_amm, rules, users):
    make_amm(
        country="SN",
        start=None,
        original_end_date=TODAY + timedelta(days=100),
        original_end_date_manual=True,
    )
    make_amm(
        country="CI",
        start=None,
        original_end_date=TODAY + timedelta(days=100),
        original_end_date_manual=True,
    )
    evaluate_rules(today=TODAY)
    return Alert.objects.all()


def test_alert_list_scope_and_filters(country_client, hq_client, open_alerts):
    assert hq_client.get("/api/v1/alerts").json()["count"] == 4
    mine = country_client.get("/api/v1/alerts").json()
    assert mine["count"] == 2 and {a["country_iso2"] for a in mine["results"]} == {"SN"}
    assert hq_client.get("/api/v1/alerts?country=CI").json()["count"] == 2
    assert hq_client.get("/api/v1/alerts?severity=WARNING").json()["count"] == 2
    assert hq_client.get("/api/v1/alerts?status=RESOLVED").json()["count"] == 0
    assert hq_client.get("/api/v1/alerts?assigned_to=me").json()["count"] == 0


def test_alert_lifecycle(country_client, hq_client, users, open_alerts):
    alert = Alert.objects.get(amm__country__iso2="SN", rule__code="J-180")
    ack = country_client.post(f"/api/v1/alerts/{alert.pk}/acknowledge", {"comment": "vu"})
    assert (
        ack.status_code == 200
        and ack.json()["status"] == "ACKNOWLEDGED"
        and ack.json()["comment"] == "vu"
    )
    assigned = hq_client.post(
        f"/api/v1/alerts/{alert.pk}/assign", {"user_id": str(users["country"].pk)}
    )
    assert assigned.status_code == 200 and assigned.json()["assigned_to_email"] == "sn@test.local"
    assert country_client.get("/api/v1/alerts?assigned_to=me").json()["count"] == 1
    resolved = country_client.post(f"/api/v1/alerts/{alert.pk}/resolve", {"comment": "traité"})
    assert resolved.status_code == 200 and resolved.json()["resolution"] == "MANUAL"
    outside = Alert.objects.get(amm__country__iso2="CI", rule__code="J-180")
    assert country_client.post(f"/api/v1/alerts/{outside.pk}/acknowledge", {}).status_code == 404


def test_alert_rules_permissions(country_client, hq_client, rules):
    assert country_client.get("/api/v1/alert-rules").status_code == 200
    assert (
        country_client.post(
            "/api/v1/alert-rules", {"code": "J-10", "offset_days": 10, "roles": [], "channels": []}
        ).status_code
        == 403
    )
    created = hq_client.post(
        "/api/v1/alert-rules",
        {
            "code": "J-10",
            "offset_days": 10,
            "severity": "INFO",
            "roles": ["CEO_ADMIN"],
            "channels": ["IN_APP"],
        },
    )
    assert created.status_code == 201
    bad = hq_client.post(
        "/api/v1/alert-rules",
        {"code": "X", "offset_days": 1, "roles": ["VIEWER"], "channels": ["SMS"]},
    )
    assert bad.status_code == 400


def test_notifications_endpoints(country_client, users, open_alerts):
    unread = country_client.get("/api/v1/notifications/unread-count").json()
    # J-180 seul : le J-365, échu depuis 265 jours, est créé mais silencieux
    # (ALERTS_DISPATCH_MAX_AGE_DAYS)
    assert unread["unread"] == 1
    listed = country_client.get("/api/v1/notifications?unread=1").json()
    assert (
        listed["count"]
        == Notification.objects.filter(user=users["country"], read_at__isnull=True).count()
    )
    first = listed["results"][0]
    read = country_client.post(f"/api/v1/notifications/{first['id']}/read")
    assert read.status_code == 200 and read.json()["is_read"] is True
    assert country_client.get("/api/v1/notifications/unread-count").json()["unread"] <= 2
    assert country_client.post("/api/v1/notifications/read-all").status_code == 200
    assert country_client.get("/api/v1/notifications/unread-count").json()["unread"] == 0


def test_email_sent_for_email_channel(open_alerts, mailoutbox):
    assert any("J-180" in message.subject for message in mailoutbox)
    assert Notification.objects.filter(channel="EMAIL", sent_at__isnull=False).exists()


def test_weekly_digest(users, open_alerts, mailoutbox):
    from apps.notifications.tasks import send_weekly_digest

    before = len(mailoutbox)
    result = send_weekly_digest(today=TODAY.isoformat())
    assert result["sent"] == 3
    assert len(mailoutbox) == before + 3
    assert "Digest hebdomadaire" in mailoutbox[-1].subject
