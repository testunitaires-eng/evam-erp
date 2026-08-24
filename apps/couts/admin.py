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

