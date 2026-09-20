"""Celery application (broker and result backend on Redis, beat schedule in settings)."""

import os

from celery import Celery
from celery.signals import before_task_publish, task_failure, task_prerun, task_success

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


@before_task_publish.connect
def _propagate_request_id(headers=None, **kwargs):
    from apps.core.observability import attach_request_id

    attach_request_id(headers=headers)


@task_prerun.connect
def _bind_request_id(task=None, task_id=None, **kwargs):
    from apps.core.observability import bind_task_context

    bind_task_context(task=task, task_id=task_id)
