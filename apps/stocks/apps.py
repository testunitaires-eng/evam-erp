from django.apps import AppConfig


class StocksConfig(AppConfig):
    name = 'apps.stocks'

    def ready(self):
        from . import signals  # noqa: F401 - enregistre le signal post_save sur MouvementStock