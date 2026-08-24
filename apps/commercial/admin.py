"""
Interface d'administration Django du module commercial.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Client)
class ClientAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Prospect)
class ProspectAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ContratClient)
class ContratClientAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Tarif)
class TarifAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Commande)
class CommandeAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.LigneCommande)
class LigneCommandeAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Facture)
class FactureAdmin(admin.ModelAdmin):
    search_fields = ()

