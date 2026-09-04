"""Project package: exposes the Celery app so tasks are discovered at Django startup."""

from .celery import app as celery_app

__all__ = ("celery_app",)
