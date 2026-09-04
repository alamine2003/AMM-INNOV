from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.realtime.publisher import publish_amm_event

from .models import Alert


@receiver(post_save, sender=Alert)
def on_alert_saved(sender, instance: Alert, created: bool, **kwargs):
    publish_amm_event(
        "alert.created" if created else "alert.updated",
        instance.amm,
        id=str(instance.pk),
        amm_id=str(instance.amm_id),
    )
