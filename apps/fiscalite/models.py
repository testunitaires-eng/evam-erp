# """
# Module Fiscalité - moteur fiscal EVAM.

# Reproduit exactement le circuit décrit dans "Matrice_fiscale_par_produit_EVAM" :

#     FICHE ARTICLE -> CODE FISCAL -> MOTEUR FISCAL -> FACTURE -> SFEC -> FACTURE CERTIFIÉE

# Règle fondamentale (à ne jamais violer côté frontend/API) :
#     Le vendeur ne choisit JAMAIS manuellement le taux de TVA, les
#     centimes additionnels ou l'accise. Ces valeurs sont toujours
#     dérivées du CodeFiscal rattaché à l'article au moment de la vente.

# Règle d'historisation (tout aussi importante) :
#     La règle fiscale appliquée à une facture doit être conservée même
#     si la matrice change après coup. C'est pourquoi CodeFiscal n'est
#     JAMAIS référencé "en direct" au moment du calcul d'une ligne de
#     facture : les taux sont recopiés (figés) sur la ligne de facture
#     elle-même (voir apps/commercial/models.py::LigneFacture). Ce
#     fichier ne contient donc que la matrice de référence ACTUELLE,
#     pas l'historique des factures déjà émises.
# """

# from django.db import models


# class CodeFiscal(models.Model):
#     """
#     Une ligne de la matrice fiscale maître EVAM (§2 du document
#     Matrice fiscale). Exemples réels du document :
#         EV-FISC-EAU-EXO : eau minérale produite au Congo, exonérée
#         EV-FISC-EAU-18  : eau ne bénéficiant pas de l'exonération
#         EV-FISC-JUS-10  : jus sucré/aromatisé, TVA + centimes + accise
#         EV-FISC-YAO-18  : yaourt, TVA + centimes, pas d'accise
#     """
#     code = models.CharField(
#         "Code fiscal", max_length=30, unique=True,
#         help_text="Ex : EV-FISC-JUS-10. Attribué manuellement (pas de numérotation automatique), il fait partie du paramétrage métier.",
#     )
#     famille_fiscale = models.CharField(
#         "Famille fiscale", max_length=150,
#         help_text="Ex : 'Jus EVAM sucré/aromatisé'. Description métier de la nature fiscale, pas du produit commercial.",
#     )
#     exonere = models.BooleanField(
#         "Exonéré de TVA", default=False,
#         help_text="Si coché, taux_tva n'est pas appliqué quel que soit son contenu (cas de l'eau minérale, sous condition de qualification officielle).",
#     )
#     taux_tva = models.DecimalField(
#         "Taux de TVA (%)", max_digits=5, decimal_places=2, default=0,
#         help_text="Ex : 18.00 pour 18%. Ignoré si 'Exonéré de TVA' est coché.",
#     )
#     taux_centimes_additionnels = models.DecimalField(
#         "Centimes additionnels (% de la TVA)", max_digits=5, decimal_places=2, default=0,
#         help_text="Le document précise que ce taux s'applique sur le MONTANT DE TVA, pas sur le prix (ex : 5% de la TVA).",
#     )
#     taux_accise = models.DecimalField(
#         "Droit d'accises (%)", max_digits=5, decimal_places=2, default=0,
#         help_text="S'applique sur le prix HT, AVANT le calcul de la TVA (l'accise entre dans la base de TVA - voir calculer_taxes()).",
#     )
#     sfec_actif = models.BooleanField(
#         "Soumis à certification SFEC", default=True,
#         help_text="Si coché, les factures utilisant ce code fiscal doivent être transmises au SFEC pour certification.",
#     )
#     situation = models.TextField(
#         "Situation / commentaire", blank=True,
#         help_text="Ex : 'Qualification eau minérale EVAM à confirmer' - traçabilité des réserves ou conditions du document source.",
#     )
#     actif = models.BooleanField("Actif", default=True)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Code fiscal"
#         verbose_name_plural = "Codes fiscaux (matrice fiscale)"
#         ordering = ["code"]

#     def __str__(self):
#         return f"{self.code} - {self.famille_fiscale}"

#     def calculer_taxes(self, montant_ht):
#         """
#         Applique exactement la séquence de calcul du document
#         (§6 et §8 : exemple jus et exemple yaourt) :

#             A. Accise = montant_ht x taux_accise
#             B. Base TVA = montant_ht + Accise   (l'accise entre dans la base taxable à la TVA)
#             C. TVA = Base TVA x taux_tva        (0 si exonéré)
#             D. Centimes additionnels = TVA x taux_centimes_additionnels
#             TOTAL TTC = montant_ht + Accise + TVA + Centimes

#         Retourne un dict avec chaque composante, prêt à être recopié
#         (figé) sur une ligne de facture - voir la règle d'historisation
#         en tête de fichier.
#         """
#         from decimal import Decimal

#         montant_ht = Decimal(montant_ht)
#         accise = (montant_ht * self.taux_accise / Decimal(100)) if self.taux_accise else Decimal(0)
#         base_tva = montant_ht + accise
#         tva = Decimal(0) if self.exonere else (base_tva * self.taux_tva / Decimal(100))
#         centimes = (tva * self.taux_centimes_additionnels / Decimal(100)) if self.taux_centimes_additionnels else Decimal(0)
#         total_ttc = montant_ht + accise + tva + centimes

#         return {
#             "montant_ht": montant_ht,
#             "montant_accise": accise,
#             "base_tva": base_tva,
#             "montant_tva": tva,
#             "montant_centimes": centimes,
#             "montant_ttc": total_ttc,
#             # Les 3 taux sont renvoyés ici pour permettre à l'appelant
#             # de les figer (historisation) sur la ligne de facture.
#             "taux_tva_applique": Decimal(0) if self.exonere else self.taux_tva,
#             "taux_accise_applique": self.taux_accise,
#             "taux_centimes_applique": self.taux_centimes_additionnels,
#         }


"""
Module Fiscalité - moteur fiscal EVAM.

Reproduit exactement le circuit décrit dans "Matrice_fiscale_par_produit_EVAM" :

    FICHE ARTICLE -> CODE FISCAL -> MOTEUR FISCAL -> FACTURE -> SFEC -> FACTURE CERTIFIÉE

Règle fondamentale (à ne jamais violer côté frontend/API) :
    Le vendeur ne choisit JAMAIS manuellement le taux de TVA, les
    centimes additionnels ou l'accise. Ces valeurs sont toujours
    dérivées du CodeFiscal rattaché à l'article au moment de la vente.

Règle d'historisation (tout aussi importante) :
    La règle fiscale appliquée à une facture doit être conservée même
    si la matrice change après coup. C'est pourquoi CodeFiscal n'est
    JAMAIS référencé "en direct" au moment du calcul d'une ligne de
    facture : les taux sont recopiés (figés) sur la ligne de facture
    elle-même (voir apps/commercial/models.py::LigneFacture). Ce
    fichier ne contient donc que la matrice de référence ACTUELLE,
    pas l'historique des factures déjà émises.
"""

from django.db import models


class FamilleFiscale(models.Model):
    """
    Liste déroulante des familles fiscales connues (§2 de la matrice
    fiscale) : "Eau minérale produite au Congo", "Jus EVAM sucré/
    aromatisé"... Table de paramétrage - l'Administrateur SI peut en
    ajouter une nouvelle sans redéploiement (voir
    initialiser_matrice_fiscale pour les valeurs de départ connues).
    """
    nom = models.CharField("Famille fiscale", max_length=150, unique=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Famille fiscale"
        verbose_name_plural = "Familles fiscales"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class CodeFiscal(models.Model):
    """
    Une ligne de la matrice fiscale maître EVAM (§2 du document
    Matrice fiscale). Exemples réels du document :
        EV-FISC-EAU-EXO : eau minérale produite au Congo, exonérée
        EV-FISC-EAU-18  : eau ne bénéficiant pas de l'exonération
        EV-FISC-JUS-10  : jus sucré/aromatisé, TVA + centimes + accise
        EV-FISC-YAO-18  : yaourt, TVA + centimes, pas d'accise
    """
    code = models.CharField(
        "Code fiscal", max_length=30, unique=True,
        help_text="Ex : EV-FISC-JUS-10. Attribué manuellement (pas de numérotation automatique), il fait partie du paramétrage métier.",
    )
    famille_fiscale = models.ForeignKey(
        FamilleFiscale, verbose_name="Famille fiscale", on_delete=models.PROTECT,
        related_name="codes_fiscaux",
        help_text="Choisie dans la liste - description métier de la nature fiscale, pas du produit commercial.",
    )
    exonere = models.BooleanField(
        "Exonéré de TVA", default=False,
        help_text="Si coché, taux_tva n'est pas appliqué quel que soit son contenu (cas de l'eau minérale, sous condition de qualification officielle).",
    )
    taux_tva = models.DecimalField(
        "Taux de TVA (%)", max_digits=5, decimal_places=2, default=0,
        help_text="Ex : 18.00 pour 18%. Ignoré si 'Exonéré de TVA' est coché.",
    )
    taux_centimes_additionnels = models.DecimalField(
        "Centimes additionnels (% de la TVA)", max_digits=5, decimal_places=2, default=0,
        help_text="Le document précise que ce taux s'applique sur le MONTANT DE TVA, pas sur le prix (ex : 5% de la TVA).",
    )
    taux_accise = models.DecimalField(
        "Droit d'accises (%)", max_digits=5, decimal_places=2, default=0,
        help_text="S'applique sur le prix HT, AVANT le calcul de la TVA (l'accise entre dans la base de TVA - voir calculer_taxes()).",
    )
    sfec_actif = models.BooleanField(
        "Soumis à certification SFEC", default=True,
        help_text="Si coché, les factures utilisant ce code fiscal doivent être transmises au SFEC pour certification.",
    )
    situation = models.TextField(
        "Situation / commentaire", blank=True,
        help_text="Ex : 'Qualification eau minérale EVAM à confirmer' - traçabilité des réserves ou conditions du document source.",
    )
    actif = models.BooleanField("Actif", default=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Code fiscal"
        verbose_name_plural = "Codes fiscaux (matrice fiscale)"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.famille_fiscale}"

    def calculer_taxes(self, montant_ht):
        """
        Applique exactement la séquence de calcul du document
        (§6 et §8 : exemple jus et exemple yaourt) :

            A. Accise = montant_ht x taux_accise
            B. Base TVA = montant_ht + Accise   (l'accise entre dans la base taxable à la TVA)
            C. TVA = Base TVA x taux_tva        (0 si exonéré)
            D. Centimes additionnels = TVA x taux_centimes_additionnels
            TOTAL TTC = montant_ht + Accise + TVA + Centimes

        Retourne un dict avec chaque composante, prêt à être recopié
        (figé) sur une ligne de facture - voir la règle d'historisation
        en tête de fichier.
        """
        from decimal import Decimal

        montant_ht = Decimal(montant_ht)
        accise = (montant_ht * self.taux_accise / Decimal(100)) if self.taux_accise else Decimal(0)
        base_tva = montant_ht + accise
        tva = Decimal(0) if self.exonere else (base_tva * self.taux_tva / Decimal(100))
        centimes = (tva * self.taux_centimes_additionnels / Decimal(100)) if self.taux_centimes_additionnels else Decimal(0)
        total_ttc = montant_ht + accise + tva + centimes

        return {
            "montant_ht": montant_ht,
            "montant_accise": accise,
            "base_tva": base_tva,
            "montant_tva": tva,
            "montant_centimes": centimes,
            "montant_ttc": total_ttc,
            # Les 3 taux sont renvoyés ici pour permettre à l'appelant
            # de les figer (historisation) sur la ligne de facture.
            "taux_tva_applique": Decimal(0) if self.exonere else self.taux_tva,
            "taux_accise_applique": self.taux_accise,
            "taux_centimes_applique": self.taux_centimes_additionnels,
        }