import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.utils import timezone

from apps.notifications.models import Notification
from apps.realtime.publisher import publish_user_event

from .models import BinderExport

logger = logging.getLogger(__name__)


def _notify(export: BinderExport) -> None:
    """Prévient le demandeur dans l'application : il n'a pas à rester sur la page."""
    if export.created_by is None:
        return
    ready = export.status == BinderExport.Status.READY
    title = (
        f"Classeur {export.binder_key} prêt : {export.decisions} décisions officielles jointes"
        if ready
        else f"Classeur {export.binder_key} : la préparation a échoué"
    )
    notification = Notification.objects.create(
        user=export.created_by,
        channel=Notification.Channel.IN_APP,
        title=title[:255],
        body=(
            f"{export.page_count} pages, {export.size_bytes // (1024 * 1024)} Mo. "
            f"{export.without_scan} AMM sans scan."
            if ready
            else export.error
        ),
        link=f"{settings.FRONTEND_URL.rstrip('/')}/classeurs/{export.binder_key}",
        sent_at=timezone.now(),
    )
    publish_user_event(export.created_by_id, "notification.created", notification.pk)


@shared_task(name="apps.binders.tasks.build_binder_export", soft_time_limit=1800, time_limit=1860)
def build_binder_export(export_id: str) -> str:
    from .export import build_export, fail

    # Prise en charge exclusive : la tâche peut être republiée par le rattrapage.
    claimed = BinderExport.objects.filter(pk=export_id, status=BinderExport.Status.PENDING).update(
        status=BinderExport.Status.RUNNING, started_at=timezone.now()
    )
    if not claimed:
        return "déjà pris en charge"
    export = BinderExport.objects.select_related("created_by").get(pk=export_id)
    try:
        build_export(export)
    except SoftTimeLimitExceeded:
        fail(export_id, "Le classeur a mis trop de temps à se préparer. Relancez la préparation.")
    except Exception as exc:
        logger.exception("Préparation du classeur %s impossible", export.binder_key)
        fail(export_id, f"Préparation impossible : {exc}")
    export.refresh_from_db()
    try:
        _notify(export)
    except Exception:
        logger.exception("Notification du classeur %s impossible", export.binder_key)
    return export.status
