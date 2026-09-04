"""Celery application (broker and result backend on Redis, beat schedule in settings)."""

import os

from celery import Celery
from celery.signals import task_failure, task_success

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("amm_innov")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@task_success.connect
def _on_task_success(sender=None, **kwargs):
    from apps.core.metrics import celery_task_finished

    celery_task_finished(getattr(sender, "name", "unknown"), "SUCCESS")


@task_failure.connect
def _on_task_failure(sender=None, **kwargs):
    from apps.core.metrics import celery_task_finished

    celery_task_finished(getattr(sender, "name", "unknown"), "FAILURE")
