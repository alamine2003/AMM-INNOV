"""Domain events: publish document changes and keep the dossier state of the AMM in step."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.realtime.publisher import publish_amm_event

from .models import Document


def _refresh_dossier_state(amm) -> None:
    """L'état du dossier suit les scans : on ne réécrit l'AMM que s'il change vraiment."""
    from apps.amm.services.status import apply_state, compute_amm_state

    if compute_amm_state(amm).differs_from(amm):
        apply_state(amm)


@receiver(post_save, sender=Document)
def on_document_saved(sender, instance: Document, created: bool, **kwargs):
    if getattr(instance, "_skip_signals", False):
        return
    publish_amm_event(
        "document.created" if created else "document.updated",
        instance.amm,
        id=str(instance.pk),
        amm_id=str(instance.amm_id),
    )
    _refresh_dossier_state(instance.amm)


@receiver(post_delete, sender=Document)
def on_document_deleted(sender, instance: Document, **kwargs):
    from apps.amm.models import MarketingAuthorization

    if getattr(instance, "_skip_signals", False):
        return
    try:
        _refresh_dossier_state(instance.amm)
    except MarketingAuthorization.DoesNotExist:
        pass  # AMM supprimée : ses documents partent avec elle.
