"""
Commande de gestion : crée un compte de démonstration pour chacun des
11 profils métier, avec le mot de passe "Demo1234!".

Usage :
    python manage.py creer_comptes_demo

Utile pour tester rapidement les permissions par rôle sans avoir à
créer manuellement un utilisateur par acteur via l'admin.
"""

from django.core.management.base import BaseCommand
from apps.comptes.models import Utilisateur, Profil


class Command(BaseCommand):
    help = "Crée un compte de démonstration pour chaque profil métier."

    def handle(self, *args, **options):
        mot_de_passe = "Demo1234!"
        for profil, libelle in Profil.choices:
            identifiant = profil.lower()
            if Utilisateur.objects.filter(username=identifiant).exists():
                self.stdout.write(f"  - {identifiant} existe déjà, ignoré")
                continue
            Utilisateur.objects.create_user(
                username=identifiant,
                password=mot_de_passe,
                first_name=libelle,
                profil=profil,
            )
            self.stdout.write(self.style.SUCCESS(f"  + {identifiant} ({libelle}) créé"))
        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé. Mot de passe pour tous les comptes : {mot_de_passe}"
        ))
