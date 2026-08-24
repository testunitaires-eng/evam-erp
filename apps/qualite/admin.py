"""
Interface d'administration Django du module qualite.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Lot)
class LotAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ControleQualite)
class ControleQualiteAdmin(admin.ModelAdmin):
    search_fields = ()

