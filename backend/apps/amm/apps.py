from django.apps import AppConfig


class AmmConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.amm"
    verbose_name = "AMM et renouvellements"

    def ready(self) -> None:
        from . import signals  # noqa: F401
