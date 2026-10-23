"""Alert engine: daily evaluation of the rules and automatic reconciliation.

- `evaluate_rules(today)`: per AMM, resolves the applicable rule per code (country rule wins
  over the global rule) and creates missing alerts, dispatching notifications for new ones.
- `reconcile(amm)`: resolves open alerts made pointless by a filed or obtained renewal.
"""

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.utils import timezone

from apps.alerts.models import Alert, AlertRule
from apps.amm.models import MarketingAuthorization, Renewal
from apps.core.dates import today as reference_today

CODE_J0 = "J0"
CODE_DOSSIER = "DOSSIER"
CODE_DECISION = "DECISION"

# Délais « ronds » comptés en mois, comme les dates affichées sur la fiche (dépôt idéal = fin − 6
# mois, limite agence = fin − 3 mois, « À renouveler » dans les 6 mois) : J-180 tombe le jour du
# dépôt idéal et J-90 le jour de la limite agence, et non 2 ou 3 jours plus tard.
OFFSET_MONTHS = {365: 12, 360: 12, 180: 6, 90: 3, 30: 1}


def deadline_due(end: date, offset_days: int) -> date:
    """Date d'une alerte d'échéance : fin − délai (en mois pour les délais ronds)."""
    months = OFFSET_MONTHS.get(offset_days)
    if months:
        return end - relativedelta(months=months)
    return end - timedelta(days=offset_days)


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
    due = deadline_due(end, rule.offset_days)
    if rule.code == CODE_DOSSIER:
        if amm.dossier_state != MarketingAuthorization.DossierState.INCOMPLET:
            return None
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

    from apps.notifications import services as notification_services

    today = today or reference_today()
    if max_age_days is None:
        max_age_days = settings.ALERTS_DISPATCH_MAX_AGE_DAYS
    rules = list(AlertRule.objects.filter(is_active=True).select_related("country"))
    created = evaluated = notified = silenced = 0
    queryset = MarketingAuthorization.objects.select_related("country").prefetch_related("renewals")
    for amm in queryset.iterator(chunk_size=500):
        evaluated += 1
        renewals = list(amm.renewals.all())
        # Alertes et notifications d'une AMM dans une seule transaction : un crash entre les deux
        # laissait une alerte sans notification, que la passe suivante trouvait déjà créée et ne
        # notifiait jamais (H11). Les e-mails partent après le commit (enqueue).
        with transaction.atomic():
            fresh: list[Alert] = []
            stale: list[Alert] = []
            for rule in applicable_rules(rules, amm.country_id):
                due = due_date_for(rule, amm, renewals, today)
                if due is None:
                    continue
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
                notification_services.dispatch(alert)
            notified += len(to_send)
            silenced += len(fresh) + len(stale) - len(to_send)
    return {"created": created, "evaluated": evaluated, "notified": notified, "silenced": silenced}


def _resolution(alert, amm, renewals) -> str | None:
    """Pourquoi une alerte ouverte n'a plus lieu d'être (None : elle reste ouverte)."""
    R = Alert.Resolution
    rule = alert.rule
    pending = any(r.workflow_status in Renewal.PENDING_STATUSES for r in renewals)
    obtained = any(
        r.workflow_status == Renewal.WorkflowStatus.OBTENU and r.end_date for r in renewals
    )
    end = amm.effective_end_date

    if rule.code == CODE_DECISION:
        if pending:
            return None
        # L'issue du dépôt qui a déclenché l'alerte : obtenu, rejeté ou abandonné.
        filed = [
            r
            for r in renewals
            if r.filing_date and r.filing_date + timedelta(days=rule.offset_days) == alert.due_date
        ]
        outcome = filed[0].workflow_status if filed else None
        if outcome == Renewal.WorkflowStatus.OBTENU or (outcome is None and obtained):
            return R.AUTO_RENEWED
        if outcome in (Renewal.WorkflowStatus.REJETE, Renewal.WorkflowStatus.ABANDONNE):
            return R.AUTO_CLOSED
        return R.MANUAL

    if rule.code == CODE_J0:
        # Un dépôt en cours ne rend pas l'AMM valide : l'alerte reste tant qu'elle est expirée.
        if amm.status != MarketingAuthorization.Status.EXPIRE:
            return R.AUTO_RENEWED if obtained else R.AUTO_UPDATED
        return R.AUTO_UPDATED if end and alert.due_date != end else None

    if (
        rule.code == CODE_DOSSIER
        and amm.dossier_state != MarketingAuthorization.DossierState.INCOMPLET
    ):
        return R.AUTO_COMPLETED
    if rule.only_if_not_filed and pending:
        return R.AUTO_FILED
    # Échéance déplacée (renouvellement obtenu, date corrigée) : l'alerte à l'ancienne date tombe,
    # la passe quotidienne la recrée à la nouvelle s'il y a lieu (pas de doublon).
    if end is None or deadline_due(end, rule.offset_days) != alert.due_date:
        months = OFFSET_MONTHS.get(rule.offset_days)
        implied_end = alert.due_date + (
            relativedelta(months=months) if months else timedelta(days=rule.offset_days)
        )
        if obtained and end and implied_end < end:
            return R.AUTO_RENEWED
        return R.AUTO_UPDATED
    return None


def reconcile(amm: MarketingAuthorization) -> int:
    """Auto-resolves open alerts. Returns the number of alerts resolved."""
    open_alerts = list(
        Alert.objects.filter(amm=amm, status__in=Alert.OPEN_STATUSES).select_related("rule")
    )
    if not open_alerts:
        return 0
    # Relecture explicite : appelée depuis un signal, l'AMM peut porter un prefetch obsolète.
    renewals = list(Renewal.objects.filter(amm_id=amm.pk))
    now = timezone.now()
    resolved = 0
    for alert in open_alerts:
        resolution = _resolution(alert, amm, renewals)
        if resolution is None:
            continue
        alert.status = Alert.Status.RESOLVED
        alert.resolution = resolution
        alert.resolved_at = now
        alert.save(update_fields=["status", "resolution", "resolved_at"])
        resolved += 1
    return resolved
