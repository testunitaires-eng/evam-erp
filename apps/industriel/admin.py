from django.contrib import admin
from . import models


class EtapeCircuitInline(admin.TabularInline):
    model = models.EtapeCircuit
    extra = 0


@admin.register(models.Circuit)
class CircuitAdmin(admin.ModelAdmin):
    list_display = ("code", "designation", "activite", "article", "ligne", "version", "statut")
    list_filter = ("activite", "statut")
    inlines = [EtapeCircuitInline]


for modele in (models.Activite, models.Usine, models.EtapeStandard, models.Ligne, models.Poste, models.Equipement):
    admin.site.register(modele)
