"""
Interface d'administration Django du module qualite.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Lot)
class LotAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ControleQualite)
class ControleQualiteAdmin(admin.ModelAdmin):
    search_fields = ()



@admin.register(models.ResultatControle)
class ResultatControleAdmin(admin.ModelAdmin):

    list_display = (
        "numero",
        "point",
        "lot",
        "valeur",
        "statut",
        "est_reprise",
        "controle_origine",
        "date_realisation",
    )

    list_filter = (
        "statut",
        "est_reprise",
        "point__parametre",
    )

    search_fields = (
        "numero",
        "lot__numero_lot",
        "point__designation",
    )

    actions = ["creer_reprises"]

    @admin.action(description="Créer une reprise pour les contrôles non conformes")
    def creer_reprises(self, request, queryset):

        compteur = 0
        erreurs = 0

        for controle in queryset:

            if controle.statut != models.StatutResultat.NON_CONFORME:
                erreurs += 1
                continue

            try:
                controle.creer_reprise()
                compteur += 1

            except ValueError as e:
                erreurs += 1
                self.message_user(
                    request,
                    f"{controle.numero} : {str(e)}",
                    level=messages.ERROR,
                )

        if compteur:
            self.message_user(
                request,
                f"{compteur} reprise(s) créée(s) avec succès.",
                level=messages.SUCCESS,
            )

        if erreurs:
            self.message_user(
                request,
                f"{erreurs} contrôle(s) ignoré(s) ou en erreur.",
                level=messages.WARNING,
            )
