"""
Interface d'administration Django du module comptabilite.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.AnomalieDetectee)
class AnomalieDetecteeAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ExportComptable)
class ExportComptableAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Cloture)
class ClotureAdmin(admin.ModelAdmin):
    search_fields = ()

