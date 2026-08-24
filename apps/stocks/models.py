"""
Module 4 - Stocks.

Gère les dépôts, les quantités par article/dépôt et tous les
mouvements physiques (entrées, sorties, transferts, ajustements).

Règle centrale du cahier des charges (§7.2) :
    quantité disponible = quantité physique - quantité bloquée - quantité réservée
"""

from django.db import models
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero


class Depot(models.Model):
    """Un lieu de stockage physique (usine, dépôt régional...)."""
    nom = models.CharField("Nom du dépôt", max_length=100)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Dépôt"
        verbose_name_plural = "Dépôts"

    def __str__(self):
        return self.nom


class StockArticle(models.Model):
    """
    La photographie de l'état du stock d'un article dans un dépôt à
    l'instant présent. Mise à jour automatiquement à chaque mouvement
    de stock (voir signal dans apps/stocks/signals.py).
    """
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.PROTECT,
        related_name="stocks",
    )
    depot = models.ForeignKey(
        Depot, verbose_name="Dépôt", on_delete=models.PROTECT,
        related_name="stocks",
    )
    quantite_physique = models.DecimalField(
        "Quantité physique", max_digits=14, decimal_places=3, default=0
    )
    quantite_bloquee = models.DecimalField(
        "Quantité bloquée", max_digits=14, decimal_places=3, default=0,
        help_text="Ex : lots non conformes en attente de décision qualité.",
    )
    quantite_reservee = models.DecimalField(
        "Quantité réservée", max_digits=14, decimal_places=3, default=0,
        help_text="Ex : réservée pour une commande client validée non encore livrée.",
    )

    class Meta:
        verbose_name = "Stock par article"
        verbose_name_plural = "Stocks par article"
        unique_together = ("article", "depot")

    def __str__(self):
        return f"{self.article.code} @ {self.depot.nom} : {self.quantite_disponible} disponible"

    @property
    def quantite_disponible(self):
        return self.quantite_physique - self.quantite_bloquee - self.quantite_reservee


class TypeMouvement(models.TextChoices):
    ENTREE = "ENTREE", "Entrée"
    SORTIE = "SORTIE", "Sortie"
    TRANSFERT = "TRANSFERT", "Transfert"
    AJUSTEMENT = "AJUSTEMENT", "Ajustement (inventaire)"
    RETOUR = "RETOUR", "Retour"


class MouvementStock(models.Model):
    """
    Trace TOUTE variation physique de stock. Rien ne modifie
    StockArticle directement : on passe toujours par un mouvement,
    qui est ensuite répercuté automatiquement (traçabilité totale,
    voir cahier des charges §16.1).
    """
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.PROTECT,
        related_name="mouvements",
    )
    depot = models.ForeignKey(
        Depot, verbose_name="Dépôt", on_delete=models.PROTECT,
        related_name="mouvements",
    )
    type_mouvement = models.CharField(
        "Type de mouvement", max_length=20, choices=TypeMouvement.choices
    )
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
    motif = models.CharField("Motif", max_length=255, blank=True)
    document_origine = models.CharField(
        "Document d'origine", max_length=100, blank=True,
        help_text="Ex : numéro d'OF, de commande, de bon de livraison à l'origine du mouvement.",
    )
    utilisateur = models.ForeignKey(
        Utilisateur, verbose_name="Effectué par", on_delete=models.PROTECT,
    )
    date_mouvement = models.DateTimeField("Date du mouvement", auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-date_mouvement"]

    def __str__(self):
        return f"{self.numero} - {self.get_type_mouvement_display()} {self.quantite} {self.article.code}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("MVT")
        super().save(*args, **kwargs)


class StatutInventaire(models.TextChoices):
    EN_COURS = "EN_COURS", "En cours"
    CLOTURE = "CLOTURE", "Clôturé"


class Inventaire(models.Model):
    """Une campagne d'inventaire physique sur un dépôt donné."""
    depot = models.ForeignKey(Depot, verbose_name="Dépôt", on_delete=models.PROTECT)
    date_inventaire = models.DateField("Date de l'inventaire")
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutInventaire.choices,
        default=StatutInventaire.EN_COURS,
    )
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Réalisé par", on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"

    def __str__(self):
        return f"Inventaire {self.depot.nom} du {self.date_inventaire}"


class LigneInventaire(models.Model):
    """
    Compare la quantité théorique (celle du système) à la quantité
    réellement comptée. L'écart déclenche un mouvement d'AJUSTEMENT.
    """
    inventaire = models.ForeignKey(
        Inventaire, verbose_name="Inventaire", on_delete=models.CASCADE,
        related_name="lignes",
    )
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    quantite_theorique = models.DecimalField("Quantité théorique", max_digits=14, decimal_places=3)
    quantite_comptee = models.DecimalField("Quantité comptée", max_digits=14, decimal_places=3)

    class Meta:
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"

    def __str__(self):
        return f"{self.inventaire} - {self.article.code}"

    @property
    def ecart(self):
        return self.quantite_comptee - self.quantite_theorique
