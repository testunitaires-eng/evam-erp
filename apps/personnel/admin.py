"""
Interface d'administration Django du module personnel.
"""

from django.contrib import admin
from . import models


class AffectationEnLigne(admin.TabularInline):
    model = models.Affectation
    extra = 0
    fields = ("etape", "poste", "ordre_fabrication", "date_debut", "date_fin", "observations")


@admin.register(models.Ouvrier)
class OuvrierAdmin(admin.ModelAdmin):
    list_display = ("matricule", "nom", "prenom", "type_contrat", "date_entree", "date_fin_contrat", "usine", "actif")
    list_filter = ("type_contrat", "actif", "usine", "competences")
    search_fields = ("matricule", "nom", "prenom", "telephone", "numero_piece")
    filter_horizontal = ("competences",)
    readonly_fields = ("matricule", "date_creation")
    inlines = [AffectationEnLigne]


@admin.register(models.Affectation)
class AffectationAdmin(admin.ModelAdmin):
    list_display = ("ouvrier", "etape", "poste", "ordre_fabrication", "date_debut", "date_fin")
    list_filter = ("etape", "ouvrier__type_contrat")
    search_fields = ("ouvrier__matricule", "ouvrier__nom", "ouvrier__prenom", "ordre_fabrication__numero")
    readonly_fields = ("affecte_par", "date_creation")
