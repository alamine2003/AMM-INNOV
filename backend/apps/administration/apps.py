from django.apps import AppConfig


class AdministrationConfig(AppConfig):
    """Administration de l'application : corbeille (et, ensuite, audit et permissions).

    Couche des fonctions transverses (docs/architecture-couches.md) : elle lit toutes les apps.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.administration"
    verbose_name = "Administration"
