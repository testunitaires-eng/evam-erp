"""Interface d'administration Django du module reporting."""

from django.contrib import admin
from . import models


@admin.register(models.RapportGenere)
class RapportGenereAdmin(admin.ModelAdmin):
    list_display = ("periode", "date_rapport", "genere_par", "date_generation")
    search_fields = ()