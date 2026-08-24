"""
Interface d'administration Django du module stocks.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Depot)
class DepotAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.StockArticle)
class StockArticleAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Inventaire)
class InventaireAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.LigneInventaire)
class LigneInventaireAdmin(admin.ModelAdmin):
    search_fields = ()

