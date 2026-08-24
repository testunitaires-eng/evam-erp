"""
Module 7 - Gestion commerciale.

Clients, prospects, contrats, tarifs, commandes et factures. Le
Commercial "consulte le stock disponible mais ne le modifie jamais"
(la modification passe uniquement par apps.stocks).
"""

from django.db import models
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero


class TypeClient(models.TextChoices):
    PARTICULIER = "PARTICULIER", "Particulier"
    SOCIETE = "SOCIETE", "Société"
    CONTRAT = "CONTRAT", "Client sous contrat"


class Client(models.Model):
    code = models.CharField("Code client", max_length=30, unique=True)
    nom = models.CharField("Nom / Raison sociale", max_length=200)
    type_client = models.CharField("Type de client", max_length=20, choices=TypeClient.choices)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    encours_autorise = models.DecimalField(
        "Encours autorisé", max_digits=14, decimal_places=2, default=0,
        help_text="Montant maximum de créance tolérée avant blocage des commandes.",
    )
    bloque = models.BooleanField("Compte bloqué", default=False)

    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"

    def __str__(self):
        return f"{self.code} - {self.nom}"


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


class ContratClient(models.Model):
    client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.CASCADE, related_name="contrats")
    date_debut = models.DateField("Date de début")
    date_fin = models.DateField("Date de fin", null=True, blank=True)
    conditions = models.TextField("Conditions particulières", blank=True)

    class Meta:
        verbose_name = "Contrat client"
        verbose_name_plural = "Contrats clients"

    def __str__(self):
        return f"Contrat {self.client.nom} ({self.date_debut})"


class Tarif(models.Model):
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


class Commande(models.Model):
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

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("CMD")
        super().save(*args, **kwargs)

    @property
    def montant_total(self):
        return sum((ligne.quantite * ligne.prix_unitaire for ligne in self.lignes.all()), start=0)


class LigneCommande(models.Model):
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


class StatutFacture(models.TextChoices):
    EMISE = "EMISE", "Émise"
    PAYEE = "PAYEE", "Payée"
    PARTIELLEMENT_PAYEE = "PARTIELLEMENT_PAYEE", "Partiellement payée"
    ANNULEE = "ANNULEE", "Annulée"


class Facture(models.Model):
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    commande = models.OneToOneField(Commande, verbose_name="Commande", on_delete=models.PROTECT, related_name="facture")
    client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT)
    montant_total = models.DecimalField("Montant total", max_digits=14, decimal_places=2)
    statut = models.CharField("Statut", max_length=25, choices=StatutFacture.choices, default=StatutFacture.EMISE)
    date_emission = models.DateTimeField("Date d'émission", auto_now_add=True)

    class Meta:
        verbose_name = "Facture"
        verbose_name_plural = "Factures"
        ordering = ["-date_emission"]

    def __str__(self):
        return f"{self.numero} - {self.client.nom} ({self.montant_total})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("FACT")
        super().save(*args, **kwargs)
