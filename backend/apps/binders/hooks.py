"""Ce que l'app Classeurs déclare au socle : rattrapage des classeurs avec décisions."""

from __future__ import annotations

from datetime import timedelta

from apps.core.registry import RECOVERY

EXPORT_PENDING_AFTER = timedelta(minutes=5)
EXPORT_RUNNING_MAX = timedelta(minutes=35)  # soft_time_limit de la tâche : 30 min


@RECOVERY.register
def recover_binder_exports(now) -> dict[str, int]:
    """Classeurs avec décisions : republie une demande restée en attente, clôt une préparation
    interrompue (redémarrage du service) pour que le siège puisse la relancer."""
    from .models import BinderExport
    from .tasks import build_binder_export

    interrupted = BinderExport.objects.filter(
        status=BinderExport.Status.RUNNING, started_at__lt=now - EXPORT_RUNNING_MAX
    ).update(
        status=BinderExport.Status.FAILED,
        finished_at=now,
        error="La préparation a été interrompue (redémarrage du service). Relancez-la.",
    )
    republished = 0
    for pk in BinderExport.objects.filter(
        status=BinderExport.Status.PENDING, created_at__lt=now - EXPORT_PENDING_AFTER
    ).values_list("pk", flat=True)[:10]:
        build_binder_export.delay(str(pk))
        republished += 1
    return {"binder_exports_interrupted": interrupted, "binder_exports_republished": republished}
