from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
    verbose_name = "Notifications"

    def ready(self) -> None:
        from . import hooks  # noqa: F401  (déclarations au socle : apps/core/registry.py)
