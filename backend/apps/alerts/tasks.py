from datetime import date

from celery import shared_task

from .services.engine import evaluate_rules


@shared_task(name="apps.alerts.tasks.evaluate_alert_rules")
def evaluate_alert_rules(today: str | None = None) -> dict:
    return evaluate_rules(today=date.fromisoformat(today) if today else None)
