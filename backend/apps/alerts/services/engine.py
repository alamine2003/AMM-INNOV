"""Alert engine: daily evaluation of the rules and automatic reconciliation.

- `evaluate_rules(today)`: per AMM, resolves the applicable rule per code (country rule wins
  over the global rule) and creates missing alerts, dispatching notifications for new ones.
- `reconcile(amm)`: resolves open alerts made pointless by a filed or obtained renewal.
"""

from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.alerts.models import Alert, AlertRule
from apps.amm.models import MarketingAuthorization, Renewal
from apps.core.dates import today as reference_today

CODE_J0 = "J0"
CODE_DOSSIER = "DOSSIER"
CODE_DECISION = "DECISION"


def applicable_rules(rules: list[AlertRule], country_id) -> list[AlertRule]:
    """Country-specific rules override the global rule with the same code."""
    by_code: dict[str, AlertRule] = {}
    for rule in rules:
        if rule.country_id is None and rule.code not in by_code:
            by_code[rule.code] = rule
    for rule in rules:
        if rule.country_id == country_id:
            by_code[rule.code] = rule
    return list(by_code.values())


def due_date_for(
    rule: AlertRule, amm: MarketingAuthorization, renewals, today: date
) -> date | None:
    """Returns the due date when the rule fires for this AMM today, else None."""
    end = amm.effective_end_date
    pending = any(r.workflow_status in Renewal.PENDING_STATUSES for r in renewals)

    if rule.code == CODE_J0:
        if amm.status != MarketingAuthorization.Status.EXPIRE or end is None:
            return None
        return end

    if rule.code == CODE_DECISION:
        for renewal in renewals:
            if renewal.workflow_status in Renewal.PENDING_STATUSES and renewal.filing_date:
                due = renewal.filing_date + timedelta(days=rule.offset_days)
                if due <= today:
                    return due
        return None

    if end is None or amm.status == MarketingAuthorization.Status.EXPIRE:
        return None
    if rule.only_if_not_filed and pending:
        return None
    if rule.code == CODE_DOSSIER:
        if amm.dossier_state != MarketingAuthorization.DossierState.INCOMPLET:
            return None
        if end > today + timedelta(days=rule.offset_days):
            return None
        return end - timedelta(days=rule.offset_days)

    due = end - timedelta(days=rule.offset_days)
    return due if due <= today else None


def evaluate_rules(
    today: date | None = None, dispatch: bool = True, max_age_days: int | None = None
) -> dict:
    """Creates the missing alerts for every AMM.

    Returns {"created", "evaluated", "notified", "silenced"}.

    Notifications go out for a new alert whose due date is at most `max_age_days` old
    (default `settings.ALERTS_DISPATCH_MAX_AGE_DAYS`). Older alerts are still created, so the
    dashboards and the alert list stay complete, but they are silenced, except the most recent
    one of an AMM that is still actionable (not expired): a freshly imported AMM expiring in
    100 days still gets its J-180 notification, while 500 AMM expired years ago get none.
    `dispatch=False` (first run at go-live, `manage.py evaluate_alerts --quiet`) silences all.
    """
    from django.conf import settings

    from apps.notifications.services import dispatch as dispatch_alert

    today = today or reference_today()
    if max_age_days is None:
        max_age_days = settings.ALERTS_DISPATCH_MAX_AGE_DAYS
    rules = list(AlertRule.objects.filter(is_active=True).select_related("country"))
    created = evaluated = notified = silenced = 0
    queryset = MarketingAuthorization.objects.select_related("country").prefetch_related("renewals")
    for amm in queryset.iterator(chunk_size=500):
        evaluated += 1
        renewals = list(amm.renewals.all())
        fresh: list[Alert] = []
        stale: list[Alert] = []
        for rule in applicable_rules(rules, amm.country_id):
            due = due_date_for(rule, amm, renewals, today)
            if due is None:
                continue
            with transaction.atomic():
                alert, was_created = Alert.objects.get_or_create(amm=amm, rule=rule, due_date=due)
            if not was_created:
                continue
            created += 1
            if (today - due).days <= max_age_days:
                fresh.append(alert)
            else:
                stale.append(alert)
        if not dispatch:
            silenced += len(fresh) + len(stale)
            continue
        to_send = list(fresh)
        if not fresh and stale and amm.status != MarketingAuthorization.Status.EXPIRE:
            to_send.append(max(stale, key=lambda a: a.due_date))
        for alert in to_send:
            dispatch_alert(alert)
        notified += len(to_send)
        silenced += len(fresh) + len(stale) - len(to_send)
    return {"created": created, "evaluated": evaluated, "notified": notified, "silenced": silenced}


def reconcile(amm: MarketingAuthorization) -> int:
    """Auto-resolves open alerts. Returns the number of alerts resolved."""
    open_alerts = list(
        Alert.objects.filter(amm=amm, status__in=Alert.OPEN_STATUSES).select_related("rule")
    )
    if not open_alerts:
        return 0
    renewals = list(amm.renewals.all())
    pending = any(r.workflow_status in Renewal.PENDING_STATUSES for r in renewals)
    obtained = [
        r for r in renewals if r.workflow_status == Renewal.WorkflowStatus.OBTENU and r.end_date
    ]
    now = timezone.now()
    resolved = 0
    for alert in open_alerts:
        resolution = None
        if alert.rule.code == CODE_DECISION:
            if not pending:
                resolution = Alert.Resolution.AUTO_RENEWED if obtained else Alert.Resolution.MANUAL
        elif pending:
            resolution = Alert.Resolution.AUTO_FILED
        elif obtained and amm.effective_end_date:
            implied_end = alert.due_date + timedelta(days=alert.rule.offset_days)
            if implied_end < amm.effective_end_date:
                resolution = Alert.Resolution.AUTO_RENEWED
        if resolution is None:
            continue
        alert.status = Alert.Status.RESOLVED
        alert.resolution = resolution
        alert.resolved_at = now
        alert.save(update_fields=["status", "resolution", "resolved_at"])
        resolved += 1
    return resolved
