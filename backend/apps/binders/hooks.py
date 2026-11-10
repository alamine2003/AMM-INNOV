"""Ce que l'app Classeurs déclare au socle : rattrapage des classeurs avec décisions."""

from __future__ import annotations

from datetime import timedelta

from apps.core.registry import RECOVERY
from apps.core.trash import TRASH_RESTORED

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


@TRASH_RESTORED.register
def follow_restored_page(entry, objects, user) -> None:
    """Page restaurée : les imports et la synchronisation la suivent de nouveau."""
    from apps.amm.models import MarketingAuthorization

    from .models import BinderDeletedPage

    for obj in objects:
        if isinstance(obj, MarketingAuthorization):
            amm = MarketingAuthorization.objects.select_related("product").get(pk=obj.pk)
            BinderDeletedPage.objects.filter(
                country_id=amm.country_id, product_key=amm.product.key
            ).delete()
