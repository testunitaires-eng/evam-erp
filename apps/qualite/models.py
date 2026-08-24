"""
Module 6 - Qualité / Traçabilité.

Contient le Lot (unité de traçabilité de toute production) et son
contrôle qualité. Règle centrale du cahier des charges :

    "Seuls les lots Libérés sont vendables."

Le statut d'un lot ne peut progresser que dans un sens précis :
EN_ATTENTE -> (CONFORME ou NON_CONFORME) -> LIBERE ou BLOQUE.
Le passage à LIBERE est réservé au Responsable Qualité.
"""

from django.db import models
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero


class StatutLot(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    CONFORME = "CONFORME", "Conforme"
    NON_CONFORME = "NON_CONFORME", "Non conforme"
    BLOQUE = "BLOQUE", "Bloqué"
    LIBERE = "LIBERE", "Libéré"


class Lot(models.Model):
    """
    Un lot = une quantité produite en une fois, traçable de bout en
    bout (matières utilisées -> OF -> lot -> stock -> commande ->
    client). Le numéro de lot est unique et généré automatiquement.
    """
    numero_lot = models.CharField(
        "Numéro de lot", max_length=30, unique=True, editable=False
    )
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.PROTECT,
        related_name="lots",
    )
    ordre_fabrication = models.ForeignKey(
        "production.OrdreFabrication", verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="lots",
        null=True, blank=True,
    )
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutLot.choices,
        default=StatutLot.EN_ATTENTE,
    )
    date_production = models.DateField("Date de production")
    date_peremption = models.DateField("Date de péremption", null=True, blank=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Lot"
        verbose_name_plural = "Lots"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero_lot} - {self.article.designation} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero_lot:
            self.numero_lot = generer_numero("LOT")
        super().save(*args, **kwargs)

    @property
    def est_vendable(self):
        """Seuls les lots Libérés sont vendables (règle du cahier des charges)."""
        return self.statut == StatutLot.LIBERE

    def bloquer(self, motif=""):
        self.statut = StatutLot.BLOQUE
        self.save()

    def liberer(self, utilisateur):
        """
        Ne peut être appelé que si le lot est Conforme.
        La vérification du profil (Responsable Qualité) se fait au
        niveau de la vue (permission_classes), pas ici.
        """
        if self.statut != StatutLot.CONFORME:
            raise ValueError(
                "Seul un lot Conforme peut être libéré. "
                "Statut actuel : " + self.get_statut_display()
            )
        self.statut = StatutLot.LIBERE
        self.save()


class ControleQualite(models.Model):
    """
    Le contrôle effectué par le Responsable Qualité sur un lot,
    qui détermine s'il devient Conforme ou Non conforme.
    """
    lot = models.OneToOneField(
        Lot, verbose_name="Lot contrôlé", on_delete=models.CASCADE,
        related_name="controle_qualite",
    )
    controleur = models.ForeignKey(
        Utilisateur, verbose_name="Contrôlé par", on_delete=models.PROTECT,
    )
    resultat = models.CharField(
        "Résultat", max_length=20,
        choices=[("CONFORME", "Conforme"), ("NON_CONFORME", "Non conforme")],
    )
    observations = models.TextField("Observations", blank=True)
    date_controle = models.DateTimeField("Date de contrôle", auto_now_add=True)

    class Meta:
        verbose_name = "Contrôle qualité"
        verbose_name_plural = "Contrôles qualité"

    def __str__(self):
        return f"Contrôle {self.lot.numero_lot} - {self.resultat}"

    def save(self, *args, **kwargs):
        """A chaque contrôle enregistré, met à jour automatiquement le
        statut du lot correspondant."""
        super().save(*args, **kwargs)
        self.lot.statut = self.resultat
        self.lot.save()
