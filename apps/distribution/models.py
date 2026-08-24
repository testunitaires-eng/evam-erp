"""
Module 9 - Distribution, logistique et livraison.

Reproduit exactement le circuit décrit en §12.3 du cahier des charges :
commande validée -> Responsable Distribution lance la préparation ->
Magasinier prépare -> Magasinier confirme la sortie -> bon de
livraison généré -> Chauffeur livre -> client signe -> Responsable
Distribution confirme la livraison.
"""

from django.db import models
from apps.comptes.models import Utilisateur
from apps.commercial.models import Commande
from apps.core.models import generer_numero


class Vehicule(models.Model):
    immatriculation = models.CharField("Immatriculation", max_length=30, unique=True)
    type_vehicule = models.CharField("Type de véhicule", max_length=100, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Véhicule"
        verbose_name_plural = "Véhicules"

    def __str__(self):
        return self.immatriculation


class Chauffeur(models.Model):
    utilisateur = models.OneToOneField(
        Utilisateur, verbose_name="Utilisateur", on_delete=models.CASCADE,
        related_name="fiche_chauffeur",
    )
    permis_numero = models.CharField("Numéro de permis", max_length=50, blank=True)

    class Meta:
        verbose_name = "Chauffeur"
        verbose_name_plural = "Chauffeurs"

    def __str__(self):
        return str(self.utilisateur)


class Depot(models.Model):
    """Dépôt logistique (peut correspondre à apps.stocks.Depot ; séparé
    ici pour ne pas créer de dépendance circulaire entre modules)."""
    nom = models.CharField("Nom", max_length=100)

    class Meta:
        verbose_name = "Dépôt (distribution)"
        verbose_name_plural = "Dépôts (distribution)"

    def __str__(self):
        return self.nom


class Tournee(models.Model):
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    chauffeur = models.ForeignKey(Chauffeur, verbose_name="Chauffeur", on_delete=models.PROTECT)
    vehicule = models.ForeignKey(Vehicule, verbose_name="Véhicule", on_delete=models.PROTECT)
    date_tournee = models.DateField("Date de la tournée")

    class Meta:
        verbose_name = "Tournée"
        verbose_name_plural = "Tournées"

    def __str__(self):
        return f"{self.numero} - {self.date_tournee}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("TRN")
        super().save(*args, **kwargs)


class StatutPreparation(models.TextChoices):
    A_PREPARER = "A_PREPARER", "À préparer"
    EN_PREPARATION = "EN_PREPARATION", "En préparation"
    PRETE = "PRETE", "Prête"
    SORTIE_MAGASIN = "SORTIE_MAGASIN", "Sortie magasin"


class PreparationLivraison(models.Model):
    """
    Étape 1 du circuit (§12.3, points 6-9) : le Responsable Distribution
    lance la préparation, le Magasinier prépare puis confirme la sortie.
    """
    commande = models.OneToOneField(
        Commande, verbose_name="Commande", on_delete=models.PROTECT,
        related_name="preparation",
    )
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutPreparation.choices,
        default=StatutPreparation.A_PREPARER,
    )
    lancee_par = models.ForeignKey(
        Utilisateur, verbose_name="Préparation lancée par (Resp. Distribution)",
        on_delete=models.PROTECT, related_name="preparations_lancees",
    )
    preparee_par = models.ForeignKey(
        Utilisateur, verbose_name="Préparée par (Magasinier)",
        on_delete=models.PROTECT, related_name="preparations_faites",
        null=True, blank=True,
    )
    date_lancement = models.DateTimeField("Date de lancement", auto_now_add=True)
    date_confirmation_sortie = models.DateTimeField("Date de sortie magasin", null=True, blank=True)

    class Meta:
        verbose_name = "Préparation de livraison"
        verbose_name_plural = "Préparations de livraison"

    def __str__(self):
        return f"Préparation {self.commande.numero} ({self.get_statut_display()})"


class StatutLivraison(models.TextChoices):
    EN_LIVRAISON = "EN_LIVRAISON", "En livraison"
    LIVREE = "LIVREE", "Livrée"
    PARTIELLEMENT_LIVREE = "PARTIELLEMENT_LIVREE", "Partiellement livrée"
    RETOURNEE = "RETOURNEE", "Retournée"


class BonLivraison(models.Model):
    """
    Étape 2 du circuit (§12.3, points 10-13) : le BL est généré après
    la sortie magasin, le chauffeur livre, le client signe, et le
    Responsable Distribution confirme la livraison finale.
    """
    numero = models.CharField("Numéro BL", max_length=30, unique=True, editable=False)
    commande = models.OneToOneField(Commande, verbose_name="Commande", on_delete=models.PROTECT, related_name="bon_livraison")
    tournee = models.ForeignKey(Tournee, verbose_name="Tournée", on_delete=models.SET_NULL, null=True, blank=True)
    statut = models.CharField("Statut", max_length=25, choices=StatutLivraison.choices, default=StatutLivraison.EN_LIVRAISON)
    signature_client = models.BooleanField("Signé par le client", default=False)
    confirme_par = models.ForeignKey(
        Utilisateur, verbose_name="Livraison confirmée par (Resp. Distribution)",
        on_delete=models.PROTECT, null=True, blank=True,
        related_name="livraisons_confirmees",
    )
    date_generation = models.DateTimeField("Date de génération", auto_now_add=True)
    date_livraison = models.DateTimeField("Date de livraison", null=True, blank=True)

    class Meta:
        verbose_name = "Bon de livraison"
        verbose_name_plural = "Bons de livraison"
        ordering = ["-date_generation"]

    def __str__(self):
        return f"{self.numero} - {self.commande.numero}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("BL")
        super().save(*args, **kwargs)


class TransfertDepot(models.Model):
    """Transfert d'un article entre deux dépôts."""
    depot_source = models.ForeignKey(Depot, verbose_name="Dépôt source", on_delete=models.PROTECT, related_name="transferts_sortants")
    depot_destination = models.ForeignKey(Depot, verbose_name="Dépôt destination", on_delete=models.PROTECT, related_name="transferts_entrants")
    date_transfert = models.DateTimeField("Date de transfert", auto_now_add=True)
    statut = models.CharField("Statut", max_length=20, default="EN_COURS")

    class Meta:
        verbose_name = "Transfert entre dépôts"
        verbose_name_plural = "Transferts entre dépôts"

    def __str__(self):
        return f"Transfert {self.depot_source} -> {self.depot_destination}"
