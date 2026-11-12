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


@admin.register(models.PrevisionVolume)
class PrevisionVolumeAdmin(admin.ModelAdmin):
    list_display = ("usine", "article", "mois_application", "bouteilles_par_mois", "saisi_par")
    list_filter = ("usine",)
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.PrevisionCaptage)
class PrevisionCaptageAdmin(admin.ModelAdmin):
    list_display = ("usine", "mois_application", "volume_site_eau_m3", "volume_autres_sites_m3", "saisi_par")
    readonly_fields = ("saisi_par", "date_saisie")


class VersionElementCoutEnLigne(admin.TabularInline):
    model = models.VersionElementCout
    extra = 0
    fields = ("mois_application", "retire", "quantite", "prix_unitaire", "frequence", "periode", "duree_vie_mois", "motif")


@admin.register(models.ElementCout)
class ElementCoutAdmin(admin.ModelAdmin):
    list_display = ("libelle", "usine", "etape", "equipement", "famille", "categorie", "ordre")
    list_filter = ("usine", "famille", "categorie", "etape")
    search_fields = ("libelle",)
    inlines = [VersionElementCoutEnLigne]


@admin.register(models.CoutStandardEau)
class CoutStandardEauAdmin(admin.ModelAdmin):
    list_display = ("usine", "mois_application", "cout_m3", "statut", "origine", "propose_par", "valide_par", "date_validation")
    list_filter = ("usine", "statut", "origine")
    readonly_fields = [champ.name for champ in models.CoutStandardEau._meta.fields]


@admin.register(models.Compteur)
class CompteurAdmin(admin.ModelAdmin):
    list_display = ("code", "libelle", "type_compteur", "usine", "site_desservi", "actif")
    list_filter = ("usine", "type_compteur", "actif")


@admin.register(models.ReleveCompteur)
class ReleveCompteurAdmin(admin.ModelAdmin):
    list_display = ("compteur", "date", "index", "saisi_par")
    list_filter = ("compteur",)
    date_hierarchy = "date"
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.ExceptionHeures)
class ExceptionHeuresAdmin(admin.ModelAdmin):
    list_display = ("date", "equipement", "ligne", "heures_en_moins", "motif", "saisi_par")
    list_filter = ("motif",)
    date_hierarchy = "date"
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.RelevePression)
class RelevePressionAdmin(admin.ModelAdmin):
    list_display = ("equipement", "date", "pression_bar", "saisi_par")
    date_hierarchy = "date"
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.PerteEau)
class PerteEauAdmin(admin.ModelAdmin):
    list_display = ("date", "usine", "cause", "type_perte", "volume_estime_m3", "article", "nombre_bouteilles", "saisi_par")
    list_filter = ("usine", "type_perte", "cause")
    date_hierarchy = "date"
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ("date", "type_intervention", "equipement", "operation", "element_remplace", "quantite_remplacee", "saisi_par")
    list_filter = ("type_intervention", "equipement__usine")
    search_fields = ("equipement__code", "description")
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.Installation)
class InstallationAdmin(admin.ModelAdmin):
    list_display = ("element", "quantite", "prix_unitaire", "duree_vie_mois", "mois_installation", "remplace", "saisi_par")
    list_filter = ("element__usine",)
    readonly_fields = ("saisi_par", "date_saisie")


@admin.register(models.AlerteEnvoyee)
class AlerteEnvoyeeAdmin(admin.ModelAdmin):
    list_display = ("cle", "date")
    search_fields = ("cle",)


@admin.register(models.ValidationSansImputation)
class ValidationSansImputationAdmin(admin.ModelAdmin):
    list_display = ("element", "mois", "motif", "valide_par")
    list_filter = ("element__usine", "mois")
    readonly_fields = ("valide_par", "date_validation")


@admin.register(models.ClotureMoisEau)
class ClotureMoisEauAdmin(admin.ModelAdmin):
    list_display = ("usine", "mois", "volume_m3", "cout_reel_total", "cout_m3", "cout_standard_m3", "ecart", "decision", "cloture_par")
    list_filter = ("usine",)

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(models.ValorisationEauOF)
class ValorisationEauOFAdmin(admin.ModelAdmin):
    list_display = ("ordre_fabrication", "cloture", "volume_m3", "cout_standard_m3", "montant_eau", "electricite_production")

    def has_change_permission(self, request, obj=None):
        return False
