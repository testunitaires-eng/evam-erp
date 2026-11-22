# """
# Interface d'administration Django du module qualite.

# Accessible sur /admin/ - pratique pour vérifier ou corriger des
# données rapidement sans passer par l'API, réservé en pratique à
# l'Administrateur SI (superutilisateur Django).
# """

# from django.contrib import admin
# from . import models

# @admin.register(models.Lot)
# class LotAdmin(admin.ModelAdmin):
#     search_fields = ()


# @admin.register(models.ControleQualite)
# class ControleQualiteAdmin(admin.ModelAdmin):
#     search_fields = ()



# @admin.register(models.ResultatControle)
# class ResultatControleAdmin(admin.ModelAdmin):

#     list_display = (
#         "numero",
#         "point",
#         "lot",
#         "valeur",
#         "statut",
#         "est_reprise",
#         "controle_origine",
#         "date_realisation",
#     )

#     list_filter = (
#         "statut",
#         "est_reprise",
#         "point__parametre",
#     )

#     search_fields = (
#         "numero",
#         "lot__numero_lot",
#         "point__designation",
#     )

#     actions = ["creer_reprises"]

#     @admin.action(description="Créer une reprise pour les contrôles non conformes")
#     def creer_reprises(self, request, queryset):

#         compteur = 0
#         erreurs = 0

#         for controle in queryset:

#             if controle.statut != models.StatutResultat.NON_CONFORME:
#                 erreurs += 1
#                 continue

#             try:
#                 controle.creer_reprise()
#                 compteur += 1

#             except ValueError as e:
#                 erreurs += 1
#                 self.message_user(
#                     request,
#                     f"{controle.numero} : {str(e)}",
#                     level=messages.ERROR,
#                 )

#         if compteur:
#             self.message_user(
#                 request,
#                 f"{compteur} reprise(s) créée(s) avec succès.",
#                 level=messages.SUCCESS,
#             )

#         if erreurs:
#             self.message_user(
#                 request,
#                 f"{erreurs} contrôle(s) ignoré(s) ou en erreur.",
#                 level=messages.WARNING,
#             )


"""
Interface d'administration Django du module Qualité.

Accessible sur /admin/

Cette interface permet :
- de gérer les lots ;
- de consulter les contrôles qualité ;
- de consulter les résultats des contrôles ;
- de créer un contrôle de reprise pour un contrôle non conforme ;
- de conserver la traçabilité entre le contrôle initial et sa reprise.

Les contrôles déjà réalisés (CONFORME, NON_CONFORME ou ANNULÉ)
restent figés et ne peuvent pas être modifiés.
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from . import models


# ============================================================
# LOTS
# ============================================================

@admin.register(models.Lot)
class LotAdmin(admin.ModelAdmin):

    list_display = (
        "numero_lot",
        "article",
        "ordre_fabrication",
        "quantite",
        "statut",
        "date_production",
        "date_peremption",
    )

    list_filter = (
        "statut",
        "date_production",
    )

    search_fields = (
        "numero_lot",
        "article__designation",
        "ordre_fabrication__numero",
    )

    readonly_fields = (
        "numero_lot",
        "date_creation",
    )

    ordering = ("-date_creation",)


# ============================================================
# CONTRÔLE QUALITÉ DES LOTS
# ============================================================

@admin.register(models.ControleQualite)
class ControleQualiteAdmin(admin.ModelAdmin):

    list_display = (
        "lot",
        "controleur",
        "resultat",
        "date_controle",
    )

    list_filter = (
        "resultat",
        "date_controle",
    )

    search_fields = (
        "lot__numero_lot",
        "lot__article__designation",
    )

    readonly_fields = (
        "date_controle",
    )


# ============================================================
# CONTRÔLES QUALITÉ RÉALISÉS
# ============================================================

@admin.register(models.ResultatControle)
class ResultatControleAdmin(admin.ModelAdmin):

    list_display = (
        "numero",
        "point",
        "ordre_fabrication",
        "lot",
        "valeur",
        "resultat_qualitatif",
        "statut",
        "est_reprise",
        "controle_origine",
        "date_prevue",
        "date_realisation",
    )

    list_filter = (
        "statut",
        "est_reprise",
        "point",
    )

    search_fields = (
        "numero",
        "point__designation",
        "lot__numero_lot",
        "ordre_fabrication__numero",
    )

    readonly_fields = (
        "numero",
        "date_creation",
        "date_realisation",
        "conforme",
    )

    ordering = (
        "-date_prevue",
        "-pk",
    )

    list_select_related = (
        "point",
        "ordre_fabrication",
        "lot",
        "controle_origine",
    )

    actions = (
        "creer_reprises",
    )

    # --------------------------------------------------------
    # ACTION ADMIN : CRÉER UNE REPRISE
    # --------------------------------------------------------

    @admin.action(
        description="Créer une reprise pour les contrôles non conformes"
    )
    def creer_reprises(self, request, queryset):

        compteur_crees = 0
        compteur_ignores = 0

        for controle in queryset:

            # ------------------------------------------------
            # Vérifier que le contrôle est non conforme
            # ------------------------------------------------

            if controle.statut != models.StatutResultat.NON_CONFORME:

                compteur_ignores += 1

                self.message_user(
                    request,
                    (
                        f"{controle.numero} : impossible de créer une reprise. "
                        f"Le contrôle n'est pas non conforme."
                    ),
                    level=messages.WARNING,
                )

                continue

            # ------------------------------------------------
            # Création de la reprise
            # ------------------------------------------------

            try:

                reprise = controle.creer_reprise()

                compteur_crees += 1

                self.message_user(
                    request,
                    (
                        f"Reprise créée avec succès : {reprise.numero}. "
                        f"Contrôle d'origine : {controle.numero}."
                    ),
                    level=messages.SUCCESS,
                )

            except (ValueError, ValidationError) as erreur:

                compteur_ignores += 1

                self.message_user(
                    request,
                    (
                        f"Erreur lors de la création de la reprise "
                        f"pour {controle.numero} : {erreur}"
                    ),
                    level=messages.ERROR,
                )

        # ----------------------------------------------------
        # Résumé de l'action
        # ----------------------------------------------------

        if compteur_crees:

            self.message_user(
                request,
                (
                    f"{compteur_crees} reprise(s) créée(s) "
                    f"avec succès."
                ),
                level=messages.SUCCESS,
            )

        if compteur_ignores:

            self.message_user(
                request,
                (
                    f"{compteur_ignores} contrôle(s) ignoré(s) "
                    f"ou ayant rencontré une erreur."
                ),
                level=messages.WARNING,
            )