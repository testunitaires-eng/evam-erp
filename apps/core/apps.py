from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Utilitaires transverses"

    def ready(self):
        # Journal de toutes les actions du système (voir apps/core/journal.py).
        from .journal import brancher
        brancher()
