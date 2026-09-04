from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.realtime.publisher import publish_amm_event

from .models import Document


@receiver(post_save, sender=Document)
def on_document_saved(sender, instance: Document, created: bool, **kwargs):
    publish_amm_event(
        "document.created" if created else "document.updated",
        instance.amm,
        id=str(instance.pk),
        amm_id=str(instance.amm_id),
    )
