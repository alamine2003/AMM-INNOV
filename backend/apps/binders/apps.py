from django.apps import AppConfig


class BindersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.binders"
    verbose_name = "Classeurs d'archivage"

    def ready(self) -> None:
        from . import hooks  # noqa: F401  (déclarations au socle : apps/core/registry.py)
