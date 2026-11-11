from django.apps import AppConfig


class AdministrationConfig(AppConfig):
    """Administration : corbeille, audit, permissions, journal des erreurs, mémoire de Redis.

    Couche des fonctions transverses (docs/architecture-couches.md) : elle lit toutes les apps.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.administration"
    verbose_name = "Administration"

    def ready(self):
        from . import hooks  # noqa: F401
