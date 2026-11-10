from django.apps import AppConfig


class DemoConfig(AppConfig):
    """Données de démonstration (`manage.py seed_demo`) : un outil qui remplit toutes les apps.

    Placée dans la couche la plus haute (voir docs/architecture-couches.md) : elle peut tout
    importer, et aucune app ne l'importe.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.demo"
    verbose_name = "Démonstration"
