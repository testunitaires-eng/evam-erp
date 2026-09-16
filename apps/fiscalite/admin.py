"""Interface d'administration Django du module fiscalité."""

from django.contrib import admin
from . import models


@admin.register(models.CodeFiscal)
class CodeFiscalAdmin(admin.ModelAdmin):
    list_display = ("code", "famille_fiscale", "exonere", "taux_tva", "taux_accise", "sfec_actif", "actif")
    search_fields = ("code", "famille_fiscale")