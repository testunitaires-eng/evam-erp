"""Interface d'administration Django du module « coût de l'eau »."""

from django.contrib import admin

from . import models


@admin.register(models.ParametresEau)
class ParametresEauAdmin(admin.ModelAdmin):
    list_display = ("usine", "mois_application", "seuil_ecart_standard_pct", "seuil_volume_minimal_pct",
                    "taux_rejet_tolere_pct", "seuil_grosse_reparation", "jour_cloture", "saisi_par")
    list_filter = ("usine",)
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.CaracteristiquesEquipement)
class CaracteristiquesEquipementAdmin(admin.ModelAdmin):
    list_display = ("equipement", "mois_application", "puissance_kw", "heures_marche_jour", "saisi_par")
    list_filter = ("equipement__usine",)
    search_fields = ("equipement__code", "equipement__designation")
    readonly_fields = ("saisi_par", "date_saisie")
