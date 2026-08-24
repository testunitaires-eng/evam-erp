"""
Interface d'administration Django du module distribution.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Chauffeur)
class ChauffeurAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Depot)
class DepotAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Tournee)
class TourneeAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.PreparationLivraison)
class PreparationLivraisonAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.BonLivraison)
class BonLivraisonAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.TransfertDepot)
class TransfertDepotAdmin(admin.ModelAdmin):
    search_fields = ()

