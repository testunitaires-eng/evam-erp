"""
Module 2 - Référentiel.

Contient tout ce qui est "paramétré une fois puis réutilisé partout" :
- Article : toute matière première, produit intermédiaire ou produit fini
- FicheTechnique : la recette / composition d'un article fabriqué
- CompositionFicheTechnique : les lignes de la recette (quel intrant, en
  quelle quantité)
- FicheConditionnement : comment un produit est emballé (carton, film,
  palette...)

Règle importante du cahier des charges : le Magasinier NE PEUT PAS
créer ou modifier une fiche technique (voir apps/comptes/permissions.py
et referentiel/views.py).
"""

from django.db import models
from apps.comptes.models import Utilisateur


class TypeArticle(models.TextChoices):
    MATIERE_PREMIERE = "MATIERE_PREMIERE", "Matière première"
    PRODUIT_INTERMEDIAIRE = "PRODUIT_INTERMEDIAIRE", "Produit intermédiaire"
    PRODUIT_FINI = "PRODUIT_FINI", "Produit fini"


class UniteMesure(models.TextChoices):
    KILOGRAMME = "KG", "Kilogramme"
    LITRE = "L", "Litre"
    UNITE = "UNITE", "Unité"
    CARTON = "CARTON", "Carton"
    PALETTE = "PALETTE", "Palette"
    METRE = "M", "Mètre"


class Article(models.Model):
    """
    Toute chose qui peut être achetée, stockée, produite ou vendue :
    matière première (ex: préforme, arôme), produit intermédiaire
    (ex: bouteille soufflée, étiquette) ou produit fini (ex: EAU 100cl).
    """
    code = models.CharField("Code article", max_length=30, unique=True)
    designation = models.CharField("Désignation", max_length=200)
    type_article = models.CharField(
        "Type d'article", max_length=30, choices=TypeArticle.choices
    )
    unite_mesure = models.CharField(
        "Unité de mesure", max_length=10, choices=UniteMesure.choices
    )
    famille = models.CharField(
        "Famille", max_length=50, blank=True,
        help_text="Ex : Eau, Jus et boissons, Yaourt, Étiquettes",
    )
    actif = models.BooleanField("Actif", default=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"


class StatutFicheTechnique(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    VALIDEE = "VALIDEE", "Validée"
    ARCHIVEE = "ARCHIVEE", "Archivée"


class FicheTechnique(models.Model):
    """
    La "recette" d'un article fabriqué : quels intrants, en quelle
    quantité, pour produire une unité de l'article.

    Versionnée : chaque nouvelle version d'une fiche technique doit
    être validée avant utilisation en production. L'historique des
    versions est conservé (rien n'est supprimé).
    """
    article = models.ForeignKey(
        Article, verbose_name="Article fabriqué",
        on_delete=models.PROTECT, related_name="fiches_techniques",
    )
    version = models.PositiveIntegerField("Version", default=1)
    statut = models.CharField(
        "Statut", max_length=20,
        choices=StatutFicheTechnique.choices,
        default=StatutFicheTechnique.BROUILLON,
    )
    cree_par = models.ForeignKey(
        Utilisateur, verbose_name="Créée par",
        on_delete=models.PROTECT, related_name="fiches_creees",
    )
    valide_par = models.ForeignKey(
        Utilisateur, verbose_name="Validée par",
        on_delete=models.PROTECT, related_name="fiches_validees",
        null=True, blank=True,
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    date_validation = models.DateTimeField("Date de validation", null=True, blank=True)

    class Meta:
        verbose_name = "Fiche technique"
        verbose_name_plural = "Fiches techniques"
        unique_together = ("article", "version")
        ordering = ["article", "-version"]

    def __str__(self):
        return f"Fiche {self.article.code} v{self.version} ({self.get_statut_display()})"

    def valider(self, utilisateur):
        """
        Fait passer la fiche de BROUILLON à VALIDEE.
        Seule une fiche validée peut être utilisée pour calculer les
        besoins matières d'un ordre de fabrication (voir apps/production).
        """
        if self.statut != StatutFicheTechnique.BROUILLON:
            raise ValueError("Seule une fiche en brouillon peut être validée.")
        self.statut = StatutFicheTechnique.VALIDEE
        self.valide_par = utilisateur
        from django.utils import timezone
        self.date_validation = timezone.now()
        self.save()


class CompositionFicheTechnique(models.Model):
    """
    Une ligne de recette : "il faut X kg/L/unités de telle matière
    pour produire une unité de l'article de la fiche technique".
    """
    fiche_technique = models.ForeignKey(
        FicheTechnique, verbose_name="Fiche technique",
        on_delete=models.CASCADE, related_name="composition",
    )
    matiere = models.ForeignKey(
        Article, verbose_name="Matière / intrant",
        on_delete=models.PROTECT, related_name="utilise_dans_fiches",
    )
    quantite_necessaire = models.DecimalField(
        "Quantité nécessaire par unité produite",
        max_digits=12, decimal_places=4,
    )

    class Meta:
        verbose_name = "Ligne de composition"
        verbose_name_plural = "Composition des fiches techniques"
        unique_together = ("fiche_technique", "matiere")

    def __str__(self):
        return f"{self.fiche_technique} : {self.quantite_necessaire} {self.matiere.unite_mesure} de {self.matiere.designation}"


class FicheConditionnement(models.Model):
    """
    Comment un produit fini est emballé pour l'expédition :
    nombre d'unités par carton, type d'emballage, poids, palettisation.
    """
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.CASCADE,
        related_name="fiches_conditionnement",
    )
    nombre_unites_par_carton = models.PositiveIntegerField("Unités par carton")
    type_emballage = models.CharField("Type d'emballage", max_length=100)
    poids_carton_kg = models.DecimalField(
        "Poids du carton (kg)", max_digits=8, decimal_places=2,
        null=True, blank=True,
    )
    nombre_cartons_par_palette = models.PositiveIntegerField(
        "Cartons par palette", null=True, blank=True,
    )

    class Meta:
        verbose_name = "Fiche de conditionnement"
        verbose_name_plural = "Fiches de conditionnement"

    def __str__(self):
        return f"Conditionnement {self.article.code}"
