"""
Interface d'administration Django du module fiscalité.
"""

from django.contrib import admin
from . import models

@admin.register(models.FamilleFiscale)
class FamilleFiscaleAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CodeFiscal)
class CodeFiscalAdmin(admin.ModelAdmin):
    search_fields = ()