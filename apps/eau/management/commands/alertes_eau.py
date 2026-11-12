"""
Alertes datées du site eau (maintenance préventive à faire, fin de vie
des pièces étalées). À planifier une fois par jour (ex : cron Railway) :
    python manage.py alertes_eau
"""

from django.core.management.base import BaseCommand

from apps.eau.maintenance import envoyer_alertes


class Command(BaseCommand):
    help = "Envoie les alertes de maintenance du site eau (chacune une seule fois)."

    def handle(self, *args, **options):
        envoyees = envoyer_alertes()
        self.stdout.write(self.style.SUCCESS(f"{envoyees} alerte(s) de maintenance envoyée(s)."))
