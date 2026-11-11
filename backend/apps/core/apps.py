from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    verbose_name = "Socle"

    def ready(self):
        from .errors import connect
        from .metrics import register_collector

        register_collector()
        connect()  # journal des erreurs (serveur et tâches de fond)
