# """
# Module 7 - Gestion commerciale.

# Clients, prospects, contrats, tarifs, commandes et factures. Le
# Commercial "consulte le stock disponible mais ne le modifie jamais"
# (la modification passe uniquement par apps.stocks).
# """

# from django.db import models
# from apps.comptes.models import Utilisateur
# from apps.referentiel.models import Article
# from apps.core.models import generer_numero


# class TypeClient(models.TextChoices):
#     PARTICULIER = "PARTICULIER", "Particulier"
#     SOCIETE = "SOCIETE", "Société"
#     CONTRAT = "CONTRAT", "Client sous contrat"


# class Client(models.Model):
#     code = models.CharField("Code client", max_length=30, unique=True)
#     nom = models.CharField("Nom / Raison sociale", max_length=200)
#     type_client = models.CharField("Type de client", max_length=20, choices=TypeClient.choices)
#     adresse = models.CharField("Adresse", max_length=255, blank=True)
#     telephone = models.CharField("Téléphone", max_length=30, blank=True)
#     encours_autorise = models.DecimalField(
#         "Encours autorisé", max_digits=14, decimal_places=2, default=0,
#         help_text="Montant maximum de créance tolérée avant blocage des commandes.",
#     )
#     delai_paiement_jours = models.PositiveIntegerField(
#         "Délai de paiement (jours)", default=0,
#         help_text="0 = paiement immédiat (comptant). Sert à calculer l'échéance des factures.",
#     )
#     bloque = models.BooleanField("Compte bloqué", default=False)

#     class Meta:
#         verbose_name = "Client"
#         verbose_name_plural = "Clients"

#     def __str__(self):
#         return f"{self.code} - {self.nom}"


# class Prospect(models.Model):
#     nom = models.CharField("Nom", max_length=200)
#     contact = models.CharField("Contact", max_length=150, blank=True)
#     statut = models.CharField("Statut", max_length=50, default="Nouveau")
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Prospect"
#         verbose_name_plural = "Prospects"

#     def __str__(self):
#         return self.nom


# class ContratClient(models.Model):
#     client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.CASCADE, related_name="contrats")
#     date_debut = models.DateField("Date de début")
#     date_fin = models.DateField("Date de fin", null=True, blank=True)
#     conditions = models.TextField("Conditions particulières", blank=True)

#     class Meta:
#         verbose_name = "Contrat client"
#         verbose_name_plural = "Contrats clients"

#     def __str__(self):
#         return f"Contrat {self.client.nom} ({self.date_debut})"


# class Tarif(models.Model):
#     """Prix de vente d'un article, éventuellement spécifique à un client sous contrat."""
#     article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
#     client = models.ForeignKey(
#         Client, verbose_name="Client (tarif spécifique)", on_delete=models.CASCADE,
#         null=True, blank=True,
#         help_text="Laisser vide pour un tarif public standard.",
#     )
#     prix_unitaire = models.DecimalField("Prix unitaire", max_digits=14, decimal_places=2)
#     date_debut_validite = models.DateField("Valide à partir du")
#     date_fin_validite = models.DateField("Valide jusqu'au", null=True, blank=True)

#     class Meta:
#         verbose_name = "Tarif"
#         verbose_name_plural = "Tarifs"

#     def __str__(self):
#         cible = self.client.nom if self.client else "Tarif public"
#         return f"{self.article.code} - {cible} : {self.prix_unitaire}"


# class TypeCommande(models.TextChoices):
#     COMPTANT = "COMPTANT", "Vente au comptant"
#     CONTRAT = "CONTRAT", "Client sous contrat"


# class StatutCommande(models.TextChoices):
#     BROUILLON = "BROUILLON", "Brouillon"
#     VALIDEE = "VALIDEE", "Validée"
#     EN_PREPARATION = "EN_PREPARATION", "En préparation"
#     LIVREE = "LIVREE", "Livrée"
#     FACTUREE = "FACTUREE", "Facturée"
#     ANNULEE = "ANNULEE", "Annulée"


# class Commande(models.Model):
#     """
#     La commande client. Sa validation déclenche automatiquement (selon
#     le type) la chaîne commerciale décrite en §10 du cahier des
#     charges : réservation stock -> encaissement/facturation ->
#     préparation -> sortie magasin -> livraison.
#     """
#     numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
#     client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT, related_name="commandes")
#     type_commande = models.CharField("Type de commande", max_length=15, choices=TypeCommande.choices)
#     statut = models.CharField(
#         "Statut", max_length=20, choices=StatutCommande.choices, default=StatutCommande.BROUILLON
#     )
#     cree_par = models.ForeignKey(Utilisateur, verbose_name="Créée par", on_delete=models.PROTECT)
#     date_commande = models.DateTimeField("Date de commande", auto_now_add=True)

#     class Meta:
#         verbose_name = "Commande"
#         verbose_name_plural = "Commandes"
#         ordering = ["-date_commande"]

#     def __str__(self):
#         return f"{self.numero} - {self.client.nom}"

#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("CMD")
#         super().save(*args, **kwargs)

#     @property
#     def montant_total(self):
#         return sum((ligne.quantite * ligne.prix_unitaire for ligne in self.lignes.all()), start=0)


# class LigneCommande(models.Model):
#     commande = models.ForeignKey(Commande, verbose_name="Commande", on_delete=models.CASCADE, related_name="lignes")
#     article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
#     quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
#     prix_unitaire = models.DecimalField("Prix unitaire", max_digits=14, decimal_places=2)

#     class Meta:
#         verbose_name = "Ligne de commande"
#         verbose_name_plural = "Lignes de commande"

#     def __str__(self):
#         return f"{self.commande.numero} : {self.quantite} {self.article.code}"

#     @property
#     def montant_ligne(self):
#         return self.quantite * self.prix_unitaire


# class StatutFacture(models.TextChoices):
#     EMISE = "EMISE", "Émise"
#     PAYEE = "PAYEE", "Payée"
#     PARTIELLEMENT_PAYEE = "PARTIELLEMENT_PAYEE", "Partiellement payée"
#     ANNULEE = "ANNULEE", "Annulée"


# # class Facture(models.Model):
# #     numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
# #     commande = models.OneToOneField(Commande, verbose_name="Commande", on_delete=models.PROTECT, related_name="facture")
# #     client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT)
# #     montant_total = models.DecimalField("Montant total", max_digits=14, decimal_places=2)
# #     statut = models.CharField("Statut", max_length=25, choices=StatutFacture.choices, default=StatutFacture.EMISE)
# #     date_emission = models.DateTimeField("Date d'émission", auto_now_add=True)

# #     class Meta:
# #         verbose_name = "Facture"
# #         verbose_name_plural = "Factures"
# #         ordering = ["-date_emission"]

# #     def __str__(self):
# #         return f"{self.numero} - {self.client.nom} ({self.montant_total})"

# #     def save(self, *args, **kwargs):
# #         if not self.numero:
# #             self.numero = generer_numero("FACT")
# #         super().save(*args, **kwargs)


# class Facture(models.Model):
#     """
#     Depuis l'introduction du moteur fiscal (apps.fiscalite), une
#     facture n'a plus de montant_total saisi à la main : il est
#     recalculé automatiquement à partir de ses LigneFacture (voir
#     recalculer_totaux()). montant_total reste un champ stocké (plutôt
#     qu'une property) pour rester filtrable/triable facilement par
#     l'API, mais il ne doit être modifié que par recalculer_totaux().
#     """
#     numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
#     commande = models.OneToOneField(Commande, verbose_name="Commande", on_delete=models.PROTECT, related_name="facture")
#     client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT)
#     montant_ht_total = models.DecimalField("Montant total HT", max_digits=14, decimal_places=2, default=0)
#     montant_taxes_total = models.DecimalField(
#         "Montant total des taxes", max_digits=14, decimal_places=2, default=0,
#         help_text="Somme accise + TVA + centimes additionnels de toutes les lignes.",
#     )
#     # montant_total = models.DecimalField("Montant total TTC", max_digits=14, decimal_places=2, default=0)
#     # statut = models.CharField("Statut", max_length=25, choices=StatutFacture.choices, default=StatutFacture.EMISE)
#     # date_emission = models.DateTimeField("Date d'émission", auto_now_add=True)

#     # class Meta:
#     #     verbose_name = "Facture"
#     #     verbose_name_plural = "Factures"
#     #     ordering = ["-date_emission"]

#     # def __str__(self):
#     #     return f"{self.numero} - {self.client.nom} ({self.montant_total})"

#     # def save(self, *args, **kwargs):
#     #     if not self.numero:
#     #         self.numero = generer_numero("FACT")
#     #     super().save(*args, **kwargs)

#     def ajouter_ligne(self, article, quantite, prix_unitaire_ht):
#         """
#         Ajoute une ligne à la facture en calculant et en FIGEANT les
#         taxes d'après le code fiscal de l'article au moment présent
#         (règle d'historisation du document fiscal : si la matrice
#         change plus tard, cette ligne garde les taux appliqués ici).

#         Lève ValueError si l'article n'a pas de code fiscal actif
#         (règle : un article non rattaché fiscalement ne peut pas être
#         facturé, voir Article.peut_etre_facture).
#         """
#         if not article.peut_etre_facture:
#             raise ValueError(
#                 f"L'article {article.code} n'a pas de code fiscal actif : "
#                 "impossible de le facturer tant qu'il n'est pas rattaché "
#                 "à un code fiscal (voir le référentiel)."
#             )
#         montant_ht_ligne = quantite * prix_unitaire_ht
#         taxes = article.code_fiscal.calculer_taxes(montant_ht_ligne)

#         ligne = LigneFacture.objects.create(
#             facture=self, article=article, quantite=quantite,
#             prix_unitaire_ht=prix_unitaire_ht, code_fiscal=article.code_fiscal,
#             taux_tva_applique=taxes["taux_tva_applique"],
#             taux_accise_applique=taxes["taux_accise_applique"],
#             taux_centimes_applique=taxes["taux_centimes_applique"],
#             montant_ht=taxes["montant_ht"], montant_accise=taxes["montant_accise"],
#             montant_tva=taxes["montant_tva"], montant_centimes=taxes["montant_centimes"],
#             montant_ttc=taxes["montant_ttc"],
#         )
#         self.recalculer_totaux()
#         return ligne

#     def recalculer_totaux(self):
#         """Recalcule montant_ht_total, montant_taxes_total et montant_total à partir des lignes existantes."""
#         lignes = self.lignes_facture.all()
#         self.montant_ht_total = sum((l.montant_ht for l in lignes), start=0)
#         self.montant_taxes_total = sum(
#             (l.montant_accise + l.montant_tva + l.montant_centimes for l in lignes), start=0
#         )
#         self.montant_total = sum((l.montant_ttc for l in lignes), start=0)
#         self.save()

#     montant_total = models.DecimalField("Montant total TTC", max_digits=14, decimal_places=2, default=0)
#     statut = models.CharField("Statut", max_length=25, choices=StatutFacture.choices, default=StatutFacture.EMISE)
#     date_emission = models.DateTimeField("Date d'émission", auto_now_add=True)
#     date_echeance = models.DateField(
#         "Date d'échéance", null=True, blank=True,
#         help_text="Calculée automatiquement à la création (date d'émission + délai de paiement du client).",
#     )

#     class Meta:
#         verbose_name = "Facture"
#         verbose_name_plural = "Factures"
#         ordering = ["-date_emission"]

#     def __str__(self):
#         return f"{self.numero} - {self.client.nom} ({self.montant_total})"

#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("FACT")
#         if not self.date_echeance:
#             from datetime import timedelta
#             from django.utils import timezone
#             self.date_echeance = (timezone.now() + timedelta(days=self.client.delai_paiement_jours)).date()
#         super().save(*args, **kwargs)

#     @property
#     def montant_paye(self):
#         """§8.5 Impayés : somme des encaissements liés à cette facture (apps.caisse.Encaissement)."""
#         from django.db.models import Sum
#         return self.encaissements.aggregate(total=Sum("montant"))["total"] or 0

#     @property
#     def solde_restant(self):
#         return self.montant_total - self.montant_paye

#     @property
#     def jours_retard(self):
#         """Nombre de jours de retard si la facture a une échéance dépassée et un solde restant > 0."""
#         from django.utils import timezone
#         if not self.date_echeance or self.solde_restant <= 0:
#             return 0
#         retard = (timezone.now().date() - self.date_echeance).days
#         return retard if retard > 0 else 0

#     @property
#     def est_impayee(self):
#         return self.solde_restant > 0 and self.jours_retard > 0


#     def generer_lignes_depuis_commande(self):
#         """
#         Génère automatiquement une ligne de facture par ligne de la
#         commande liée, en reprenant l'article et le prix déjà saisis
#         sur la commande (règle §15 du cahier des charges : pas de
#         ressaisie). Le prix de LigneCommande est considéré HT.
#         """
#         for ligne_commande in self.commande.lignes.all():
#             self.ajouter_ligne(
#                 article=ligne_commande.article,
#                 quantite=ligne_commande.quantite,
#                 prix_unitaire_ht=ligne_commande.prix_unitaire,
#             )


# class LigneFacture(models.Model):
#     """
#     Une ligne de facture, avec les taux fiscaux FIGÉS au moment de sa
#     création (voir Facture.ajouter_ligne). `code_fiscal` est conservé
#     comme référence de traçabilité (quel code a été utilisé), mais ce
#     sont bien les 3 champs taux_..._applique et les montants calculés
#     ci-dessous qui font foi sur cette ligne - pas une relecture en
#     direct de CodeFiscal, qui a pu changer depuis.
#     """
#     facture = models.ForeignKey(
#         Facture, verbose_name="Facture", on_delete=models.CASCADE,
#         related_name="lignes_facture",
#     )
#     article = models.ForeignKey("referentiel.Article", verbose_name="Article", on_delete=models.PROTECT)
#     quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
#     prix_unitaire_ht = models.DecimalField("Prix unitaire HT", max_digits=14, decimal_places=2)
#     code_fiscal = models.ForeignKey(
#         "fiscalite.CodeFiscal", verbose_name="Code fiscal utilisé", on_delete=models.PROTECT,
#         help_text="Référence du code fiscal au moment de la facturation (traçabilité).",
#     )

#     # Taux figés (historisation - voir docstring de la classe)
#     taux_tva_applique = models.DecimalField("Taux de TVA appliqué (%)", max_digits=5, decimal_places=2)
#     taux_accise_applique = models.DecimalField("Taux d'accise appliqué (%)", max_digits=5, decimal_places=2)
#     taux_centimes_applique = models.DecimalField("Taux de centimes additionnels appliqué (%)", max_digits=5, decimal_places=2)

#     # Montants calculés et figés
#     montant_ht = models.DecimalField("Montant HT", max_digits=14, decimal_places=2)
#     montant_accise = models.DecimalField("Montant accise", max_digits=14, decimal_places=2)
#     montant_tva = models.DecimalField("Montant TVA", max_digits=14, decimal_places=2)
#     montant_centimes = models.DecimalField("Montant centimes additionnels", max_digits=14, decimal_places=2)
#     montant_ttc = models.DecimalField("Montant TTC", max_digits=14, decimal_places=2)

#     class Meta:
#         verbose_name = "Ligne de facture"
#         verbose_name_plural = "Lignes de facture"

#     def __str__(self):
#         return f"{self.facture.numero} : {self.quantite} x {self.article.code} = {self.montant_ttc} TTC"





# class StatutAvoir(models.TextChoices):
#     EMIS = "EMIS", "Émis"
#     UTILISE = "UTILISE", "Utilisé"
#     ANNULE = "ANNULE", "Annulé"


# class Avoir(models.Model):
#     """
#     §8.1/§9B : crédit accordé à un client, à valoir sur une prochaine
#     commande ou facture. Peut être créé manuellement (correction de
#     facture) ou automatiquement suite à une réclamation (voir
#     apps.reclamations.SolutionClient, type AVOIR).
#     """
#     numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
#     client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT, related_name="avoirs")
#     facture_origine = models.ForeignKey(
#         Facture, verbose_name="Facture d'origine", on_delete=models.SET_NULL,
#         null=True, blank=True, related_name="avoirs_emis",
#     )
#     montant = models.DecimalField("Montant de l'avoir", max_digits=14, decimal_places=2)
#     motif = models.TextField("Motif")
#     statut = models.CharField("Statut", max_length=15, choices=StatutAvoir.choices, default=StatutAvoir.EMIS)
#     facture_utilisation = models.ForeignKey(
#         Facture, verbose_name="Facture d'utilisation", on_delete=models.SET_NULL,
#         null=True, blank=True, related_name="avoirs_utilises",
#     )
#     cree_par = models.ForeignKey(Utilisateur, verbose_name="Créé par", on_delete=models.PROTECT)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)
#     date_utilisation = models.DateTimeField("Date d'utilisation", null=True, blank=True)

#     class Meta:
#         verbose_name = "Avoir"
#         verbose_name_plural = "Avoirs"
#         ordering = ["-date_creation"]

#     def __str__(self):
#         return f"{self.numero} - {self.client.nom} ({self.montant}, {self.get_statut_display()})"

#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("AVO")
#         super().save(*args, **kwargs)

#     def utiliser(self, facture_cible):
#         """Applique l'avoir sur une facture (crédit) - un avoir ne s'utilise qu'une fois."""
#         from django.utils import timezone
#         if self.statut != StatutAvoir.EMIS:
#             raise ValueError(f"Cet avoir est {self.get_statut_display().lower()}, il ne peut plus être utilisé.")
#         if facture_cible.client_id != self.client_id:
#             raise ValueError("Cet avoir n'appartient pas au client de cette facture.")
#         self.facture_utilisation = facture_cible
#         self.statut = StatutAvoir.UTILISE
#         self.date_utilisation = timezone.now()
#         self.save()



"""
Module 7 - Gestion commerciale.

Clients, prospects, contrats, tarifs, commandes et factures. Le
Commercial "consulte le stock disponible mais ne le modifie jamais"
(la modification passe uniquement par apps.stocks).
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_ordre_dates,
    valeur_en_base, verifier_transition,
)


class TypeClient(models.TextChoices):
    PARTICULIER = "PARTICULIER", "Particulier"
    SOCIETE = "SOCIETE", "Société"
    CONTRAT = "CONTRAT", "Client sous contrat"


class Client(ValidationAvantEnregistrement, models.Model):
    code = models.CharField("Code client", max_length=30, unique=True)
    nom = models.CharField("Nom / Raison sociale", max_length=200)
    type_client = models.CharField("Type de client", max_length=20, choices=TypeClient.choices)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    encours_autorise = models.DecimalField(
        "Encours autorisé", max_digits=14, decimal_places=2, default=0,
        help_text="Montant maximum de créance tolérée avant blocage des commandes.",
    )
    delai_paiement_jours = models.PositiveIntegerField(
        "Délai de paiement (jours)", default=0,
        help_text="0 = paiement immédiat (comptant). Sert à calculer l'échéance des factures.",
    )
    bloque = models.BooleanField("Compte bloqué", default=False)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self):
        return f"{self.code} - {self.nom}"

    def clean(self):
        exiger_positif(self.encours_autorise, "encours_autorise", "L'encours autorisé", strict=False)

    @property
    def encours_actuel(self):
        """
        Somme des soldes restants sur toutes les factures non annulées
        du client (utilise Facture.solde_restant, qui tient déjà
        compte des encaissements et paiements partiels).
        """
        from decimal import Decimal
        total = Decimal("0")
        for facture in self.facture_set.exclude(statut=StatutFacture.ANNULEE):
            total += facture.solde_restant
        return total

    def verifier_peut_commander(self, montant_commande=None):
        """
        Lève ValidationError si le client ne peut pas passer/faire
        progresser une commande. Point d'entrée UNIQUE de la règle
        métier "un client bloqué ou en dépassement d'encours ne peut
        plus commander" - appelé depuis Commande.save() (donc quelle
        que soit la voie d'entrée : API, admin Django, shell, script).
        """
        from django.core.exceptions import ValidationError
        from decimal import Decimal

        if self.bloque:
            raise ValidationError(
                f"Le client « {self.nom} » est bloqué et ne peut plus passer de commande."
            )

        montant_commande = Decimal(str(montant_commande or 0))
        futur_encours = self.encours_actuel + montant_commande
        if futur_encours > self.encours_autorise:
            raise ValidationError(
                f"Encours autorisé dépassé pour « {self.nom} » : "
                f"encours actuel {self.encours_actuel} FCFA + commande {montant_commande} FCFA "
                f"dépasse le plafond de {self.encours_autorise} FCFA."
            )


class Prospect(models.Model):
    nom = models.CharField("Nom", max_length=200)
    contact = models.CharField("Contact", max_length=150, blank=True)
    statut = models.CharField("Statut", max_length=50, default="Nouveau")
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Prospect"
        verbose_name_plural = "Prospects"

    def __str__(self):
        return self.nom


class ContratClient(ValidationAvantEnregistrement, models.Model):
    client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.CASCADE, related_name="contrats")
    date_debut = models.DateField("Date de début")
    date_fin = models.DateField("Date de fin", null=True, blank=True)
    conditions = models.TextField("Conditions particulières", blank=True)

    class Meta:
        verbose_name = "Contrat client"
        verbose_name_plural = "Contrats clients"

    def __str__(self):
        return f"Contrat {self.client.nom} ({self.date_debut})"

    def clean(self):
        exiger_ordre_dates(self.date_debut, self.date_fin, "date_fin", "la date de début", "La date de fin")


class Tarif(ValidationAvantEnregistrement, models.Model):
    """Prix de vente d'un article, éventuellement spécifique à un client sous contrat."""
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    client = models.ForeignKey(
        Client, verbose_name="Client (tarif spécifique)", on_delete=models.CASCADE,
        null=True, blank=True,
        help_text="Laisser vide pour un tarif public standard.",
    )
    prix_unitaire = models.DecimalField("Prix unitaire", max_digits=14, decimal_places=2)
    date_debut_validite = models.DateField("Valide à partir du")
    date_fin_validite = models.DateField("Valide jusqu'au", null=True, blank=True)

    class Meta:
        verbose_name = "Tarif"
        verbose_name_plural = "Tarifs"

    def __str__(self):
        cible = self.client.nom if self.client else "Tarif public"
        return f"{self.article.code} - {cible} : {self.prix_unitaire}"

    def clean(self):
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire")
        exiger_ordre_dates(
            self.date_debut_validite, self.date_fin_validite, "date_fin_validite",
            "la date de début de validité", "La date de fin de validité",
        )


class TypeCommande(models.TextChoices):
    COMPTANT = "COMPTANT", "Vente au comptant"
    CONTRAT = "CONTRAT", "Client sous contrat"


class StatutCommande(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    VALIDEE = "VALIDEE", "Validée"
    EN_PREPARATION = "EN_PREPARATION", "En préparation"
    LIVREE = "LIVREE", "Livrée"
    FACTUREE = "FACTUREE", "Facturée"
    ANNULEE = "ANNULEE", "Annulée"


class Commande(ValidationAvantEnregistrement, models.Model):
    """
    La commande client. Sa validation déclenche automatiquement (selon
    le type) la chaîne commerciale décrite en §10 du cahier des
    charges : réservation stock -> encaissement/facturation ->
    préparation -> sortie magasin -> livraison.
    """
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT, related_name="commandes")
    type_commande = models.CharField("Type de commande", max_length=15, choices=TypeCommande.choices)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutCommande.choices, default=StatutCommande.BROUILLON
    )
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Créée par", on_delete=models.PROTECT)
    date_commande = models.DateTimeField("Date de commande", auto_now_add=True)

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"
        ordering = ["-date_commande"]

    def __str__(self):
        return f"{self.numero} - {self.client.nom}"

    # Workflow autorisé des statuts (§10 du cahier des charges).
    TRANSITIONS = {
        StatutCommande.BROUILLON: {StatutCommande.VALIDEE, StatutCommande.ANNULEE},
        StatutCommande.VALIDEE: {StatutCommande.BROUILLON, StatutCommande.EN_PREPARATION, StatutCommande.ANNULEE},
        StatutCommande.EN_PREPARATION: {StatutCommande.LIVREE},
        StatutCommande.LIVREE: {StatutCommande.FACTUREE},
    }

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("CMD")
        super().save(*args, **kwargs)

    @property
    def est_modifiable(self):
        """Les lignes ne peuvent être ajoutées/modifiées que tant que la commande n'est pas partie en préparation."""
        return self.statut in (StatutCommande.BROUILLON, StatutCommande.VALIDEE)

    def a_une_facture(self):
        return self.pk is not None and Facture.objects.filter(commande_id=self.pk).exists()

    def clean(self):
        """
        Règles métier (obligatoires côté backend, quelle que soit la voie
        d'entrée : API, admin Django, shell) :
        - une commande annulée ou facturée est figée ;
        - le statut ne suit que le workflow autorisé (TRANSITIONS) ;
        - client et type ne changent plus après le brouillon ;
        - une commande ne peut être validée que si elle a au moins une ligne ;
        - une commande facturée doit avoir sa facture ; une commande
          déjà facturée ne peut pas être annulée ;
        - client bloqué ou encours dépassé : aucune commande tant
          qu'elle est en brouillon/validée et pas encore facturée (une
          fois facturée, son montant est déjà compté dans l'encours).
        """
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutCommande.ANNULEE, StatutCommande.FACTUREE):
            raise ValidationError(
                f"La commande {self.numero} est {dict(StatutCommande.choices)[ancien_statut].lower()} : "
                "elle ne peut plus être modifiée."
            )
        if ancien_statut is None and self.statut != StatutCommande.BROUILLON:
            raise ValidationError({"statut": "Une commande est toujours créée en brouillon, puis validée une fois ses lignes saisies."})
        verifier_transition(ancien_statut, self.statut, self.TRANSITIONS, "statut de commande")

        if ancien_statut not in (None, StatutCommande.BROUILLON):
            if valeur_en_base(self, "client") != self.client_id:
                raise ValidationError({"client": "Le client ne peut plus être changé une fois la commande validée."})
            if valeur_en_base(self, "type_commande") != self.type_commande:
                raise ValidationError({"type_commande": "Le type ne peut plus être changé une fois la commande validée."})

        if self.statut != ancien_statut:
            if self.statut == StatutCommande.VALIDEE and (self.pk is None or not self.lignes.exists()):
                raise ValidationError({"statut": "Impossible de valider une commande sans aucune ligne."})
            if self.statut == StatutCommande.FACTUREE and not self.a_une_facture():
                raise ValidationError({"statut": "Impossible de passer la commande à « Facturée » : aucune facture n'a été émise."})
            if self.statut == StatutCommande.ANNULEE and Facture.objects.filter(
                commande_id=self.pk,
            ).exclude(statut=StatutFacture.ANNULEE).exists():
                raise ValidationError({"statut": "Cette commande a une facture active : annulez d'abord la facture."})

        if self.client_id and self.est_modifiable and not self.a_une_facture():
            montant = self.montant_total if self.pk else 0
            self.client.verifier_peut_commander(montant_commande=montant)

    def verifier_suppression(self):
        if self.statut != StatutCommande.BROUILLON:
            raise ValidationError(
                "Seule une commande en brouillon peut être supprimée ; sinon, annulez-la."
            )

    @property
    def montant_total(self):
        if self.pk is None:
            return 0
        return sum((ligne.quantite * ligne.prix_unitaire for ligne in self.lignes.all()), start=0)


class LigneCommande(ValidationAvantEnregistrement, models.Model):
    commande = models.ForeignKey(Commande, verbose_name="Commande", on_delete=models.CASCADE, related_name="lignes")
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
    prix_unitaire = models.DecimalField("Prix unitaire", max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de commande"
        verbose_name_plural = "Lignes de commande"

    def __str__(self):
        return f"{self.commande.numero} : {self.quantite} {self.article.code}"

    @property
    def montant_ligne(self):
        return self.quantite * self.prix_unitaire

    def clean(self):
        """
        Tout est vérifié AVANT l'enregistrement de la ligne (auparavant
        la ligne était enregistrée puis l'encours contrôlé : en cas de
        dépassement, erreur 500 mais ligne conservée).
        """
        exiger_positif(self.quantite, "quantite", "La quantité")
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire")
        if self.article_id and not self.article.actif:
            raise ValidationError({"article": f"L'article {self.article.code} est inactif : il ne peut pas être commandé."})

        if self.pk:
            ancienne_commande = Commande.objects.filter(pk=valeur_en_base(self, "commande")).first()
            if ancienne_commande and not ancienne_commande.est_modifiable:
                raise ValidationError(
                    f"La commande {ancienne_commande.numero} est {ancienne_commande.get_statut_display().lower()} : "
                    "ses lignes ne peuvent plus être modifiées."
                )
        if not self.commande_id:
            return
        commande = self.commande
        if not commande.est_modifiable:
            raise ValidationError({"commande": (
                f"La commande {commande.numero} est {commande.get_statut_display().lower()} : "
                "on ne peut plus y ajouter ou modifier de ligne."
            )})
        if commande.a_une_facture():
            raise ValidationError({"commande": f"La commande {commande.numero} est déjà facturée : ses lignes sont figées."})

        if self.quantite is not None and self.prix_unitaire is not None:
            autres_lignes = commande.lignes.exclude(pk=self.pk) if self.pk else commande.lignes.all()
            montant_estime = sum((l.montant_ligne for l in autres_lignes), start=0) + self.montant_ligne
            commande.client.verifier_peut_commander(montant_commande=montant_estime)

    def verifier_suppression(self):
        commande = self.commande
        if not commande.est_modifiable or commande.a_une_facture():
            raise ValidationError(
                f"La commande {commande.numero} est {commande.get_statut_display().lower()} : "
                "ses lignes ne peuvent plus être supprimées."
            )
        if commande.statut == StatutCommande.VALIDEE and commande.lignes.count() <= 1:
            raise ValidationError(
                "Impossible de supprimer la dernière ligne d'une commande validée "
                "(repassez-la en brouillon ou annulez-la)."
            )

    def save(self, *args, **kwargs):
        # clean() (via ValidationAvantEnregistrement) a déjà tout vérifié
        # avant l'écriture ; la revalidation de la commande se fait dans
        # la même transaction : si elle échoue, la ligne n'est pas gardée.
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.commande.save()


class StatutFacture(models.TextChoices):
    EMISE = "EMISE", "Émise"
    PAYEE = "PAYEE", "Payée"
    PARTIELLEMENT_PAYEE = "PARTIELLEMENT_PAYEE", "Partiellement payée"
    ANNULEE = "ANNULEE", "Annulée"


# class Facture(models.Model):
#     numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
#     commande = models.OneToOneField(Commande, verbose_name="Commande", on_delete=models.PROTECT, related_name="facture")
#     client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT)
#     montant_total = models.DecimalField("Montant total", max_digits=14, decimal_places=2)
#     statut = models.CharField("Statut", max_length=25, choices=StatutFacture.choices, default=StatutFacture.EMISE)
#     date_emission = models.DateTimeField("Date d'émission", auto_now_add=True)
#
#     class Meta:
#         verbose_name = "Facture"
#         verbose_name_plural = "Factures"
#         ordering = ["-date_emission"]
#
#     def __str__(self):
#         return f"{self.numero} - {self.client.nom} ({self.montant_total})"
#
#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("FACT")
#         super().save(*args, **kwargs)


class Facture(ValidationAvantEnregistrement, models.Model):
    """
    Depuis l'introduction du moteur fiscal (apps.fiscalite), une
    facture n'a plus de montant_total saisi à la main : il est
    recalculé automatiquement à partir de ses LigneFacture (voir
    recalculer_totaux()). montant_total reste un champ stocké (plutôt
    qu'une property) pour rester filtrable/triable facilement par
    l'API, mais il ne doit être modifié que par recalculer_totaux().
    """
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    commande = models.OneToOneField(Commande, verbose_name="Commande", on_delete=models.PROTECT, related_name="facture")
    client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT)
    montant_ht_total = models.DecimalField("Montant total HT", max_digits=14, decimal_places=2, default=0)
    montant_taxes_total = models.DecimalField(
        "Montant total des taxes", max_digits=14, decimal_places=2, default=0,
        help_text="Somme accise + TVA + centimes additionnels de toutes les lignes.",
    )
    # montant_total = models.DecimalField("Montant total TTC", max_digits=14, decimal_places=2, default=0)
    # statut = models.CharField("Statut", max_length=25, choices=StatutFacture.choices, default=StatutFacture.EMISE)
    # date_emission = models.DateTimeField("Date d'émission", auto_now_add=True)

    # class Meta:
    #     verbose_name = "Facture"
    #     verbose_name_plural = "Factures"
    #     ordering = ["-date_emission"]

    # def __str__(self):
    #     return f"{self.numero} - {self.client.nom} ({self.montant_total})"

    # def save(self, *args, **kwargs):
    #     if not self.numero:
    #         self.numero = generer_numero("FACT")
    #     super().save(*args, **kwargs)

    @transaction.atomic
    def ajouter_ligne(self, article, quantite, prix_unitaire_ht):
        """
        Ajoute une ligne à la facture en calculant et en FIGEANT les
        taxes d'après le code fiscal de l'article au moment présent
        (règle d'historisation du document fiscal : si la matrice
        change plus tard, cette ligne garde les taux appliqués ici).

        Lève ValueError si l'article n'a pas de code fiscal actif
        (règle : un article non rattaché fiscalement ne peut pas être
        facturé, voir Article.peut_etre_facture).
        """
        if self.statut == StatutFacture.ANNULEE:
            raise ValueError("Cette facture est annulée : on ne peut plus y ajouter de ligne.")
        if quantite is None or quantite <= 0:
            raise ValueError(f"Quantité invalide pour l'article {article.code} : elle doit être supérieure à 0.")
        if prix_unitaire_ht is None or prix_unitaire_ht <= 0:
            raise ValueError(f"Prix invalide pour l'article {article.code} : il doit être supérieur à 0.")
        if not article.peut_etre_facture:
            raise ValueError(
                f"L'article {article.code} n'a pas de code fiscal actif : "
                "impossible de le facturer tant qu'il n'est pas rattaché "
                "à un code fiscal (voir le référentiel)."
            )
        montant_ht_ligne = quantite * prix_unitaire_ht
        taxes = article.code_fiscal.calculer_taxes(montant_ht_ligne)

        ligne = LigneFacture.objects.create(
            facture=self, article=article, quantite=quantite,
            prix_unitaire_ht=prix_unitaire_ht, code_fiscal=article.code_fiscal,
            taux_tva_applique=taxes["taux_tva_applique"],
            taux_accise_applique=taxes["taux_accise_applique"],
            taux_centimes_applique=taxes["taux_centimes_applique"],
            montant_ht=taxes["montant_ht"], montant_accise=taxes["montant_accise"],
            montant_tva=taxes["montant_tva"], montant_centimes=taxes["montant_centimes"],
            montant_ttc=taxes["montant_ttc"],
        )
        self.recalculer_totaux()
        return ligne

    def recalculer_totaux(self):
        """Recalcule montant_ht_total, montant_taxes_total et montant_total à partir des lignes existantes."""
        lignes = self.lignes_facture.all()
        self.montant_ht_total = sum((l.montant_ht for l in lignes), start=0)
        self.montant_taxes_total = sum(
            (l.montant_accise + l.montant_tva + l.montant_centimes for l in lignes), start=0
        )
        self.montant_total = sum((l.montant_ttc for l in lignes), start=0)
        self.save()

    montant_total = models.DecimalField("Montant total TTC", max_digits=14, decimal_places=2, default=0)
    statut = models.CharField("Statut", max_length=25, choices=StatutFacture.choices, default=StatutFacture.EMISE)
    date_emission = models.DateTimeField("Date d'émission", auto_now_add=True)
    date_echeance = models.DateField(
        "Date d'échéance", null=True, blank=True,
        help_text="Calculée automatiquement à la création (date d'émission + délai de paiement du client).",
    )

    class Meta:
        verbose_name = "Facture"
        verbose_name_plural = "Factures"
        ordering = ["-date_emission"]

    def __str__(self):
        return f"{self.numero} - {self.client.nom} ({self.montant_total})"

    def clean(self):
        """
        - la facture reprend obligatoirement le client de sa commande ;
        - on ne facture qu'une commande validée (ou en préparation / livrée)
          comportant au moins une ligne ;
        - commande et client ne changent plus après émission ;
        - une facture annulée est figée ; une facture ayant reçu un
          paiement (encaissement ou avoir) ne peut pas être annulée.
        """
        if self.commande_id and not self.client_id:
            self.client = self.commande.client
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutFacture.ANNULEE:
            raise ValidationError(f"La facture {self.numero} est annulée : elle ne peut plus être modifiée.")

        if self.pk is None:
            if self.commande_id:
                commande = self.commande
                if commande.statut not in (
                    StatutCommande.VALIDEE, StatutCommande.EN_PREPARATION, StatutCommande.LIVREE,
                ):
                    raise ValidationError({"commande": (
                        f"La commande {commande.numero} est {commande.get_statut_display().lower()} : "
                        "seule une commande validée, en préparation ou livrée peut être facturée."
                    )})
                if not commande.lignes.exists():
                    raise ValidationError({"commande": f"La commande {commande.numero} n'a aucune ligne à facturer."})
        else:
            if valeur_en_base(self, "commande") != self.commande_id:
                raise ValidationError({"commande": "La commande d'une facture émise ne peut pas être changée."})
            if valeur_en_base(self, "client") != self.client_id:
                raise ValidationError({"client": "Le client d'une facture émise ne peut pas être changé."})

        if self.commande_id and self.client_id and self.client_id != self.commande.client_id:
            raise ValidationError({"client": "Le client de la facture doit être celui de la commande."})

        if self.statut == StatutFacture.ANNULEE and ancien_statut != StatutFacture.ANNULEE and self.pk:
            if self.montant_paye > 0:
                raise ValidationError({"statut": (
                    "Impossible d'annuler une facture qui a déjà reçu un paiement "
                    f"({self.montant_paye} FCFA) : émettez plutôt un avoir."
                )})

    def verifier_suppression(self):
        if self.lignes_facture.exists() or self.encaissements.exists():
            raise ValidationError(
                "Une facture émise ne se supprime pas (document fiscal) : annulez-la ou émettez un avoir."
            )

    def mettre_a_jour_statut_paiement(self):
        """Recalcule le statut (Émise / Partiellement payée / Payée) d'après les paiements reçus."""
        if self.statut == StatutFacture.ANNULEE:
            return
        paye = self.montant_paye
        if paye > 0 and paye >= self.montant_total:
            nouveau = StatutFacture.PAYEE
        elif paye > 0:
            nouveau = StatutFacture.PARTIELLEMENT_PAYEE
        else:
            nouveau = StatutFacture.EMISE
        if nouveau != self.statut:
            self.statut = nouveau
            self.save(update_fields=["statut"])

    def save(self, *args, **kwargs):
        if self.commande_id and not self.client_id:
            self.client = self.commande.client
        if not self.numero:
            self.numero = generer_numero("FACT")
        if not self.date_echeance and self.client_id:
            from datetime import timedelta
            from django.utils import timezone
            self.date_echeance = (timezone.now() + timedelta(days=self.client.delai_paiement_jours)).date()
        super().save(*args, **kwargs)

    @property
    def montant_paye(self):
        """
        §8.5 Impayés : somme des encaissements liés à cette facture
        (apps.caisse.Encaissement) + avoirs utilisés sur cette facture
        (un avoir utilisé est un crédit qui réduit ce que le client doit).
        """
        from django.db.models import Sum
        if self.pk is None:
            return 0
        encaisse = self.encaissements.aggregate(total=Sum("montant"))["total"] or 0
        avoirs = self.avoirs_utilises.filter(statut=StatutAvoir.UTILISE).aggregate(total=Sum("montant"))["total"] or 0
        return encaisse + avoirs

    @property
    def solde_restant(self):
        return self.montant_total - self.montant_paye

    @property
    def jours_retard(self):
        """Nombre de jours de retard si la facture a une échéance dépassée et un solde restant > 0."""
        from django.utils import timezone
        if not self.date_echeance or self.solde_restant <= 0:
            return 0
        retard = (timezone.now().date() - self.date_echeance).days
        return retard if retard > 0 else 0

    @property
    def est_impayee(self):
        return self.solde_restant > 0 and self.jours_retard > 0


    @transaction.atomic
    def generer_lignes_depuis_commande(self):
        """
        Génère automatiquement une ligne de facture par ligne de la
        commande liée, en reprenant l'article et le prix déjà saisis
        sur la commande (règle §15 du cahier des charges : pas de
        ressaisie). Le prix de LigneCommande est considéré HT.

        Tout ou rien : tous les articles sont vérifiés AVANT de créer la
        moindre ligne (auparavant, si le 2e article n'avait pas de code
        fiscal, la 1re ligne restait créée : facture partielle).
        """
        if self.statut == StatutFacture.ANNULEE:
            raise ValueError("Cette facture est annulée : impossible de générer ses lignes.")
        if self.lignes_facture.exists():
            raise ValueError("Les lignes de cette facture ont déjà été générées.")
        lignes_commande = list(self.commande.lignes.select_related("article", "article__code_fiscal"))
        if not lignes_commande:
            raise ValueError(f"La commande {self.commande.numero} n'a aucune ligne à facturer.")
        non_facturables = [l.article.code for l in lignes_commande if not l.article.peut_etre_facture]
        if non_facturables:
            raise ValueError(
                "Articles sans code fiscal actif, impossible de facturer : "
                + ", ".join(non_facturables) + " (voir le référentiel)."
            )
        for ligne_commande in lignes_commande:
            self.ajouter_ligne(
                article=ligne_commande.article,
                quantite=ligne_commande.quantite,
                prix_unitaire_ht=ligne_commande.prix_unitaire,
            )


class LigneFacture(models.Model):
    """
    Une ligne de facture, avec les taux fiscaux FIGÉS au moment de sa
    création (voir Facture.ajouter_ligne). `code_fiscal` est conservé
    comme référence de traçabilité (quel code a été utilisé), mais ce
    sont bien les 3 champs taux_..._applique et les montants calculés
    ci-dessous qui font foi sur cette ligne - pas une relecture en
    direct de CodeFiscal, qui a pu changer depuis.
    """
    facture = models.ForeignKey(
        Facture, verbose_name="Facture", on_delete=models.CASCADE,
        related_name="lignes_facture",
    )
    article = models.ForeignKey("referentiel.Article", verbose_name="Article", on_delete=models.PROTECT)
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
    prix_unitaire_ht = models.DecimalField("Prix unitaire HT", max_digits=14, decimal_places=2)
    code_fiscal = models.ForeignKey(
        "fiscalite.CodeFiscal", verbose_name="Code fiscal utilisé", on_delete=models.PROTECT,
        help_text="Référence du code fiscal au moment de la facturation (traçabilité).",
    )

    # Taux figés (historisation - voir docstring de la classe)
    taux_tva_applique = models.DecimalField("Taux de TVA appliqué (%)", max_digits=5, decimal_places=2)
    taux_accise_applique = models.DecimalField("Taux d'accise appliqué (%)", max_digits=5, decimal_places=2)
    taux_centimes_applique = models.DecimalField("Taux de centimes additionnels appliqué (%)", max_digits=5, decimal_places=2)

    # Montants calculés et figés
    montant_ht = models.DecimalField("Montant HT", max_digits=14, decimal_places=2)
    montant_accise = models.DecimalField("Montant accise", max_digits=14, decimal_places=2)
    montant_tva = models.DecimalField("Montant TVA", max_digits=14, decimal_places=2)
    montant_centimes = models.DecimalField("Montant centimes additionnels", max_digits=14, decimal_places=2)
    montant_ttc = models.DecimalField("Montant TTC", max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de facture"
        verbose_name_plural = "Lignes de facture"

    def __str__(self):
        return f"{self.facture.numero} : {self.quantite} x {self.article.code} = {self.montant_ttc} TTC"


class StatutAvoir(models.TextChoices):
    EMIS = "EMIS", "Émis"
    UTILISE = "UTILISE", "Utilisé"
    ANNULE = "ANNULE", "Annulé"


class Avoir(ValidationAvantEnregistrement, models.Model):
    """
    §8.1/§9B : crédit accordé à un client, à valoir sur une prochaine
    commande ou facture. Peut être créé manuellement (correction de
    facture) ou automatiquement suite à une réclamation (voir
    apps.reclamations.SolutionClient, type AVOIR).
    """
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT, related_name="avoirs")
    facture_origine = models.ForeignKey(
        Facture, verbose_name="Facture d'origine", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="avoirs_emis",
    )
    montant = models.DecimalField("Montant de l'avoir", max_digits=14, decimal_places=2)
    motif = models.TextField("Motif")
    statut = models.CharField("Statut", max_length=15, choices=StatutAvoir.choices, default=StatutAvoir.EMIS)
    facture_utilisation = models.ForeignKey(
        Facture, verbose_name="Facture d'utilisation", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="avoirs_utilises",
    )
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Créé par", on_delete=models.PROTECT)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    date_utilisation = models.DateTimeField("Date d'utilisation", null=True, blank=True)

    class Meta:
        verbose_name = "Avoir"
        verbose_name_plural = "Avoirs"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero} - {self.client.nom} ({self.montant}, {self.get_statut_display()})"

    TRANSITIONS = {StatutAvoir.EMIS: {StatutAvoir.UTILISE, StatutAvoir.ANNULE}}

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("AVO")
        super().save(*args, **kwargs)

    def clean(self):
        exiger_positif(self.montant, "montant", "Le montant de l'avoir")
        if not (self.motif or "").strip():
            raise ValidationError({"motif": "Le motif de l'avoir est obligatoire."})
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutAvoir.UTILISE, StatutAvoir.ANNULE):
            raise ValidationError(f"Cet avoir est {dict(StatutAvoir.choices)[ancien_statut].lower()} : il ne peut plus être modifié.")
        verifier_transition(ancien_statut, self.statut, self.TRANSITIONS, "statut d'avoir", initial=StatutAvoir.EMIS)
        if self.facture_origine_id:
            facture = self.facture_origine
            if self.client_id and facture.client_id != self.client_id:
                raise ValidationError({"facture_origine": "La facture d'origine n'appartient pas à ce client."})
            if self.montant is not None and self.montant > facture.montant_total:
                raise ValidationError({"montant": (
                    f"Le montant de l'avoir ({self.montant}) dépasse le montant de la facture "
                    f"d'origine ({facture.montant_total})."
                )})

    def verifier_suppression(self):
        if self.statut != StatutAvoir.EMIS:
            raise ValidationError("Un avoir utilisé ou annulé ne peut pas être supprimé.")

    @transaction.atomic
    def utiliser(self, facture_cible):
        """Applique l'avoir sur une facture (crédit) - un avoir ne s'utilise qu'une fois."""
        from django.utils import timezone
        if self.statut != StatutAvoir.EMIS:
            raise ValueError(f"Cet avoir est {self.get_statut_display().lower()}, il ne peut plus être utilisé.")
        if facture_cible.client_id != self.client_id:
            raise ValueError("Cet avoir n'appartient pas au client de cette facture.")
        if facture_cible.statut == StatutFacture.ANNULEE:
            raise ValueError("Impossible d'utiliser un avoir sur une facture annulée.")
        if self.montant > facture_cible.solde_restant:
            raise ValueError(
                f"Le montant de l'avoir ({self.montant}) dépasse le solde restant dû "
                f"sur la facture {facture_cible.numero} ({facture_cible.solde_restant})."
            )
        self.facture_utilisation = facture_cible
        self.statut = StatutAvoir.UTILISE
        self.date_utilisation = timezone.now()
        self.save()
        facture_cible.mettre_a_jour_statut_paiement()
