"""
Interface d'administration Django du module production.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.PlanProduction)
class PlanProductionAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.OrdreFabrication)
class OrdreFabricationAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.BesoinMatierePrevu)
class BesoinMatierePrevuAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.SortieMatiere)
class SortieMatiereAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.RetourMatiere)
class RetourMatiereAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.EtapeProduction)
class EtapeProductionAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.PerteProduction)
class PerteProductionAdmin(admin.ModelAdmin):
    search_fields = ()

