"""
Interface d'administration Django du module réclamations.
"""

from django.contrib import admin
from . import models

@admin.register(models.ReclamationClient)
class ReclamationClientAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.RetourPhysique)
class RetourPhysiqueAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ControleRetour)
class ControleRetourAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Reconditionnement)
class ReconditionnementAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CoutRetourPerte)
class CoutRetourPerteAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.SolutionClient)
class SolutionClientAdmin(admin.ModelAdmin):
    search_fields = ()