"""Alert engine: creation, idempotence, auto-resolution, J0 and DOSSIER rules."""

from datetime import timedelta

import pytest

from apps.alerts.models import Alert, AlertRule
from apps.alerts.services.engine import evaluate_rules, reconcile
from apps.amm.services.workflow import transition
from apps.notifications.models import Notification
from tests.conftest import TODAY

pytestmark = pytest.mark.django_db


def codes(amm):
    return sorted(Alert.objects.filter(amm=amm).values_list("rule__code", flat=True))


def test_j180_created_once(make_amm, rules, users):
    amm = make_amm(
        start=None, original_end_date=TODAY + timedelta(days=170), original_end_date_manual=True
    )
    first = evaluate_rules(today=TODAY)
    assert first["created"] == 2  # J-365 and J-180
    assert codes(amm) == ["J-180", "J-365"]
    second = evaluate_rules(today=TODAY)
    assert second["created"] == 0
    assert Alert.objects.filter(amm=amm).count() == 2
    alert = Alert.objects.get(amm=amm, rule__code="J-180")
    assert alert.due_date == amm.effective_end_date - timedelta(days=180)
    # notifications: country user (SN) + HQ on J-180, in-app + email
    assert Notification.objects.filter(alert=alert, user=users["country"]).count() == 2
    assert Notification.objects.filter(alert=alert, user=users["hq"]).count() == 2
    assert not Notification.objects.filter(alert=alert, user=users["ceo"]).exists()


def test_country_user_outside_scope_not_notified(make_amm, rules, users):
    amm = make_amm(
        country="CI",
        start=None,
        original_end_date=TODAY + timedelta(days=100),
        original_end_date_manual=True,
    )
    evaluate_rules(today=TODAY)
    assert Alert.objects.filter(amm=amm, rule__code="J-180").exists()
    assert not Notification.objects.filter(user=users["country"]).exists()
    assert Notification.objects.filter(user=users["hq"], channel="EMAIL").exists()


def test_alerts_resolved_after_filing(make_amm, make_renewal, rules):
    amm = make_amm(
        start=None, original_end_date=TODAY + timedelta(days=80), original_end_date_manual=True
    )
    evaluate_rules(today=TODAY)
    assert codes(amm) == ["J-180", "J-365", "J-90"]
    renewal = make_renewal(amm, "EN_PREPARATION")
    assert Alert.objects.filter(amm=amm, status="OPEN").count() == 3
    transition(renewal, "DEPOSE", filing_date=TODAY)
    resolved = Alert.objects.filter(amm=amm, status="RESOLVED")
    assert resolved.count() == 3
    assert set(resolved.values_list("resolution", flat=True)) == {"AUTO_FILED"}
    # once filed, the not-filed rules do not fire again
    assert evaluate_rules(today=TODAY)["created"] == 0


def test_alerts_resolved_after_renewal_obtained(make_amm, make_renewal, rules):
    amm = make_amm(
        start=None, original_end_date=TODAY + timedelta(days=20), original_end_date_manual=True
    )
    evaluate_rules(today=TODAY)
    assert "J-30" in codes(amm)
    make_renewal(amm, "OBTENU", number="R", start_date=TODAY)
    amm.refresh_from_db()
    assert amm.status == "VALIDE"
    assert set(Alert.objects.filter(amm=amm).values_list("resolution", flat=True)) == {
        "AUTO_RENEWED"
    }


def test_j0_on_expired(make_amm, rules):
    amm = make_amm(
        start=None, original_end_date=TODAY - timedelta(days=3), original_end_date_manual=True
    )
    assert amm.status == "EXPIRE"
    evaluate_rules(today=TODAY)
    assert codes(amm) == ["J0"]
    alert = Alert.objects.get(amm=amm)
    assert alert.due_date == amm.effective_end_date


def test_dossier_rule(make_amm, rules):
    incomplete = make_amm(
        start=None,
        original_end_date=TODAY + timedelta(days=250),
        original_end_date_manual=True,
        dossier_state="INCOMPLET",
    )
    far = make_amm(
        start=None,
        original_end_date=TODAY + timedelta(days=400),
        original_end_date_manual=True,
        dossier_state="INCOMPLET",
    )
    complete = make_amm(
        start=None, original_end_date=TODAY + timedelta(days=250), original_end_date_manual=True
    )
    evaluate_rules(today=TODAY)
    assert "DOSSIER" in codes(incomplete)
    assert "DOSSIER" not in codes(far)
    assert "DOSSIER" not in codes(complete)


def test_country_rule_overrides_global(make_amm, rules, countries):
    AlertRule.objects.create(
        code="J-180",
        country=countries["SN"],
        offset_days=200,
        severity="WARNING",
        roles=["HQ_REGULATORY"],
        channels=["IN_APP"],
    )
    amm_sn = make_amm(
        country="SN",
        start=None,
        original_end_date=TODAY + timedelta(days=190),
        original_end_date_manual=True,
    )
    amm_ml = make_amm(
        country="ML",
        start=None,
        original_end_date=TODAY + timedelta(days=190),
        original_end_date_manual=True,
    )
    evaluate_rules(today=TODAY)
    assert "J-180" in codes(amm_sn)
    assert "J-180" not in codes(amm_ml)


def test_reconcile_without_alerts_is_noop(make_amm):
    assert reconcile(make_amm()) == 0
