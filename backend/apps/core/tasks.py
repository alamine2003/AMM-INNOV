"""Helper to enqueue a Celery task after the current transaction commits.

In eager mode (tests) the task runs immediately so that results are observable.
"""

from django.conf import settings
from django.db import transaction


def enqueue(task, *args, **kwargs) -> None:
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        task.apply(args=args, kwargs=kwargs)
        return
    transaction.on_commit(lambda: task.delay(*args, **kwargs))
