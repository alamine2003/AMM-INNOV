import uuid

from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Channel(models.TextChoices):
        IN_APP = "IN_APP", "In-app"
        EMAIL = "EMAIL", "Email"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    alert = models.ForeignKey(
        "alerts.Alert",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    channel = models.CharField("canal", max_length=16, choices=Channel.choices)
    title = models.CharField("titre", max_length=255)
    body = models.TextField("contenu", blank=True)
    link = models.CharField("lien", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField("envoyée le", null=True, blank=True)
    read_at = models.DateTimeField("lue le", null=True, blank=True)

    class Meta:
        verbose_name = "notification"
        verbose_name_plural = "notifications"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} → {self.user}: {self.title}"

    @property
    def is_read(self) -> bool:
        return self.read_at is not None
