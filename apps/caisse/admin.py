"""
Interface d'administration Django du module caisse.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Caisse)
class CaisseAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.SessionCaisse)
class SessionCaisseAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Encaissement)
class EncaissementAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.EcartCaisse)
class EcartCaisseAdmin(admin.ModelAdmin):
    search_fields = ()

