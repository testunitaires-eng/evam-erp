"""
Interface d'administration Django du module achats.
"""

from django.contrib import admin
from . import models

@admin.register(models.Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ContratFournisseur)
class ContratFournisseurAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ArticleFournisseur)
class ArticleFournisseurAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.BesoinApprovisionnement)
class BesoinApprovisionnementAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.DemandeAchat)
class DemandeAchatAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CommandeFournisseur)
class CommandeFournisseurAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.LigneCommandeFournisseur)
class LigneCommandeFournisseurAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ReceptionAchat)
class ReceptionAchatAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.LigneReceptionAchat)
class LigneReceptionAchatAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.RetourFournisseur)
class RetourFournisseurAdmin(admin.ModelAdmin):
    search_fields = ()

