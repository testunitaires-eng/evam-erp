"""
Interface d'administration Django du module couts.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.CoutMatiere)
class CoutMatiereAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CoutEnergie)
class CoutEnergieAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CoutMainOeuvre)
class CoutMainOeuvreAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Amortissement)
class AmortissementAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CoutStandard)
class CoutStandardAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CoutReel)
class CoutReelAdmin(admin.ModelAdmin):
    search_fields = ()



@admin.register(models.FactureCharge)
class FactureChargeAdmin(admin.ModelAdmin):
    list_display = ("numero", "reference", "periode", "montant_total")
    list_filter = ("periode",)
    search_fields = ("numero", "reference", "fournisseur")


@admin.register(models.VolumeEauSite)
class VolumeEauSiteAdmin(admin.ModelAdmin):
    list_display = ("periode", "usine", "activite", "volume_m3", "statut_donnee", "source")
    list_filter = ("periode", "usine", "statut_donnee")


@admin.register(models.ValeurCle)
class ValeurCleAdmin(admin.ModelAdmin):
    list_display = ("inducteur", "usine", "activite", "valeur", "date_debut", "source")
    list_filter = ("inducteur", "usine")


@admin.register(models.ReleveElectricite)
class ReleveElectriciteAdmin(admin.ModelAdmin):
    list_display = ("periode", "etape", "nature", "usine", "activite", "kwh", "statut_donnee", "source")
    list_filter = ("periode", "etape", "statut_donnee")
