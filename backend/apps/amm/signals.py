"""Domain events: keep the AMM state up to date, reconcile alerts, publish WebSocket events."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.realtime.publisher import publish_amm_event, publish_dashboard_refresh

from .models import MarketingAuthorization, Renewal
from .services.status import apply_state


@receiver(post_save, sender=MarketingAuthorization)
def on_amm_saved(sender, instance: MarketingAuthorization, created: bool, **kwargs):
    if getattr(instance, "_skip_signals", False):
        return
    from apps.alerts.services.engine import reconcile

    reconcile(instance)
    publish_amm_event("amm.created" if created else "amm.updated", instance)
    publish_dashboard_refresh()


@receiver(post_delete, sender=MarketingAuthorization)
def on_amm_deleted(sender, instance: MarketingAuthorization, **kwargs):
    publish_amm_event("amm.deleted", instance)
    publish_dashboard_refresh()


@receiver(post_save, sender=Renewal)
def on_renewal_saved(sender, instance: Renewal, created: bool, **kwargs):
    if getattr(instance, "_skip_signals", False):
        return
    amm = instance.amm
    if getattr(instance, "_transition_actor", None) is not None:
        amm._history_user = instance._transition_actor
    apply_state(amm)  # triggers on_amm_saved -> reconcile + amm.updated
    if hasattr(instance, "_transition_from"):
        publish_amm_event(
            "renewal.transitioned",
            amm,
            id=str(instance.pk),
            amm_id=str(amm.pk),
            from_status=instance._transition_from,
            to_status=instance.workflow_status,
        )
        del instance._transition_from


@receiver(post_delete, sender=Renewal)
def on_renewal_deleted(sender, instance: Renewal, **kwargs):
    try:
        apply_state(instance.amm)
    except MarketingAuthorization.DoesNotExist:
        pass
