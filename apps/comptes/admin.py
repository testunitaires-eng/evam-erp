"""
Interface d'administration Django du module comptes.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Utilisateur)
class UtilisateurAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.MatriceDroit)
class MatriceDroitAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.JournalAction)
class JournalActionAdmin(admin.ModelAdmin):
    search_fields = ()

