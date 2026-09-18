"""
Remplit les listes déroulantes du référentiel (familles, formats,
parfums, unités de vente) avec les valeurs connues décrites dans le
document "Proposition de fiche article EVAM" et la matrice fiscale.

À lancer UNE FOIS après la migration :
    python manage.py initialiser_referentiel_valeurs

Ces listes ne sont pas figées dans le code : l'Administrateur SI peut
en ajouter (nouveau parfum, nouveau format...) directement depuis
l'admin ou l'API, sans redéploiement. Cette commande ne fait que poser
le point de départ documenté.
"""

from django.core.management.base import BaseCommand
from apps.referentiel.models import FamilleArticle, FormatArticle, Parfum, UniteVenteArticle


FAMILLES = ["Eau", "Jus", "Yaourt", "Emballage", "Consommable"]

FORMATS = ["70 cl", "100 cl", "150 cl", "125 g"]

PARFUMS = ["Nature", "Grenadine", "Orange", "Banane", "Ananas", "Mangue", "Vanille", "Fraise", "Sucré", "Autre"]

UNITES_VENTE = ["Unité", "Pack de 8", "Pack de 16", "Carton de 12", "Pot"]


class Command(BaseCommand):
    help = "Initialise les listes déroulantes du référentiel (familles, formats, parfums, unités de vente)."

    def handle(self, *args, **options):
        total = 0
        for nom in FAMILLES:
            _, cree = FamilleArticle.objects.get_or_create(nom=nom)
            total += cree
            if cree:
                self.stdout.write(self.style.SUCCESS(f"  + Famille : {nom}"))

        for valeur in FORMATS:
            _, cree = FormatArticle.objects.get_or_create(valeur=valeur)
            total += cree
            if cree:
                self.stdout.write(self.style.SUCCESS(f"  + Format : {valeur}"))

        for nom in PARFUMS:
            _, cree = Parfum.objects.get_or_create(nom=nom)
            total += cree
            if cree:
                self.stdout.write(self.style.SUCCESS(f"  + Parfum : {nom}"))

        for nom in UNITES_VENTE:
            _, cree = UniteVenteArticle.objects.get_or_create(nom=nom)
            total += cree
            if cree:
                self.stdout.write(self.style.SUCCESS(f"  + Unité de vente : {nom}"))

        self.stdout.write(self.style.SUCCESS(f"\nTerminé : {total} valeurs créées."))