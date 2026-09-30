"""
Contrôles automatiques périodiques (impayés, stock sous minimum, lots
périmés, sessions de caisse oubliées, décaissements en attente).
À planifier une fois par jour (ex : cron Railway) :
    python manage.py detecter_anomalies
"""

from django.core.management.base import BaseCommand

from apps.comptabilite.anomalies import detecter_anomalies


class Command(BaseCommand):
    help = "Détecte les anomalies périodiques et résout celles qui ont disparu."

    def handle(self, *args, **options):
        creees, resolues = detecter_anomalies()
        self.stdout.write(self.style.SUCCESS(f"{creees} anomalie(s) détectée(s), {resolues} résolue(s) automatiquement."))
