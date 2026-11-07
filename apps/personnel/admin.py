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


@admin.register(models.ConditionRemuneration)
class ConditionRemunerationAdmin(admin.ModelAdmin):
    list_display = ("ouvrier", "mode", "montant", "periodicite_paie", "date_effet")
    list_filter = ("mode", "periodicite_paie")
    search_fields = ("ouvrier__matricule", "ouvrier__nom", "ouvrier__prenom")
    readonly_fields = ("saisi_par", "date_creation")


@admin.register(models.Pointage)
class PointageAdmin(admin.ModelAdmin):
    list_display = ("date", "ouvrier", "presence", "absence_justifiee", "etape", "ordre_fabrication", "statut")
    list_filter = ("statut", "presence", "absence_justifiee", "date")
    search_fields = ("ouvrier__matricule", "ouvrier__nom", "ouvrier__prenom", "ordre_fabrication__numero")
    date_hierarchy = "date"
    readonly_fields = ("statut", "saisi_par", "valide_par", "date_validation")


@admin.register(models.EtatPaie)
class EtatPaieAdmin(admin.ModelAdmin):
    list_display = ("numero", "ouvrier", "periodicite", "date_debut", "date_fin", "jours_travailles", "montant", "statut")
    list_filter = ("statut", "periodicite")
    search_fields = ("numero", "ouvrier__matricule", "ouvrier__nom", "ouvrier__prenom")
    date_hierarchy = "date_debut"

    def has_change_permission(self, request, obj=None):
        return False   # le circuit (préparer, valider, payer, annuler) passe par l'API
