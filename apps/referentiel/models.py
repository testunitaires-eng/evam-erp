
# """
# Module 2 - Référentiel.

# Contient tout ce qui est "paramétré une fois puis réutilisé partout" :
# - Article : toute matière première, produit intermédiaire ou produit fini
# - FicheTechnique : la recette / composition d'un article fabriqué
# - CompositionFicheTechnique : les lignes de la recette (quel intrant, en
#   quelle quantité)
# - FicheConditionnement : comment un produit est emballé (carton, film,
#   palette...)
# - ControleQualiteRequis : la liste des contrôles qualité ATTENDUS pour
#   un produit (paramétrage), distinct du contrôle réellement effectué

# Règle importante du cahier des charges : le Magasinier NE PEUT PAS
# créer ou modifier une fiche technique (voir apps/comptes/permissions.py
# et referentiel/views.py).
# """

# from django.db import models
# from apps.comptes.models import Utilisateur
# from apps.fiscalite.models import CodeFiscal


# class TypeArticle(models.TextChoices):
#     MATIERE_PREMIERE = "MATIERE_PREMIERE", "Matière première"
#     PRODUIT_INTERMEDIAIRE = "PRODUIT_INTERMEDIAIRE", "Produit intermédiaire"
#     PRODUIT_FINI = "PRODUIT_FINI", "Produit fini"


# class UniteMesure(models.TextChoices):
#     KILOGRAMME = "KG", "Kilogramme"
#     LITRE = "L", "Litre"
#     UNITE = "UNITE", "Unité"
#     CARTON = "CARTON", "Carton"
#     PALETTE = "PALETTE", "Palette"
#     METRE = "M", "Mètre"


# class Article(models.Model):
#     """
#     Toute chose qui peut être achetée, stockée, produite ou vendue :
#     matière première (ex: préforme, arôme), produit intermédiaire
#     (ex: bouteille soufflée, étiquette) ou produit fini (ex: EAU 100cl).

#     Fiche maître du produit (voir "Proposition de fiche article EVAM") :
#     regroupe les paramètres de production, stock, qualité, commercial,
#     fiscalité et comptabilité analytique, pour que chaque module les
#     réutilise sans ressaisie (règle fondamentale du cahier des charges,
#     §15 : "une information saisie ne doit pas être ressaisie ailleurs").
#     """
#     # --- Bloc 1 : Identité du produit ---
#     code = models.CharField("Code article", max_length=30, unique=True)
#     designation = models.CharField("Désignation", max_length=200)
#     type_article = models.CharField(
#         "Type d'article", max_length=30, choices=TypeArticle.choices
#     )
#     famille = models.CharField(
#         "Famille", max_length=50, blank=True,
#         help_text="Ex : Eau, Jus et boissons, Yaourt, Étiquettes",
#     )
#     sous_famille = models.CharField("Sous-famille", max_length=50, blank=True)
#     marque = models.CharField("Marque", max_length=50, blank=True, default="EVAM")
#     format = models.CharField(
#         "Format", max_length=30, blank=True,
#         help_text="Ex : 70 cl, 100 cl, 125 g",
#     )
#     parfum = models.CharField(
#         "Parfum / variante", max_length=50, blank=True,
#         help_text="Ex : Grenadine, Nature, Fraise (vide si non applicable)",
#     )
#     unite_mesure = models.CharField(
#         "Unité de base", max_length=10, choices=UniteMesure.choices,
#         help_text="Unité de gestion interne (ex : Unité pour une bouteille).",
#     )
#     unite_vente = models.CharField(
#         "Unité de vente", max_length=50, blank=True,
#         help_text="Ex : Pack de 8, Carton de 12 - l'unité réellement facturée au client.",
#     )
#     actif = models.BooleanField("Actif", default=True)

#     # --- Bloc 2 : Fiscalité ---
#     # Volontairement une simple FK, jamais un taux en clair sur
#     # l'article : le vendeur ne doit jamais pouvoir modifier un taux
#     # à la volée (règle du document fiscal). Nullable pour ne pas
#     # bloquer la création d'un article en attendant son rattachement
#     # fiscal, mais voir Article.peut_etre_facture ci-dessous : un
#     # article sans code fiscal ne doit pas pouvoir être facturé.
#     code_fiscal = models.ForeignKey(
#         CodeFiscal, verbose_name="Code fiscal", on_delete=models.PROTECT,
#         null=True, blank=True, related_name="articles",
#         help_text="Détermine automatiquement la TVA, l'accise et les centimes additionnels appliqués à la facturation.",
#     )

#     # --- Bloc 6 : Stock & traçabilité ---
#     suivi_par_lot = models.BooleanField(
#         "Suivi par lot", default=True,
#         help_text="Un produit fabriqué doit presque toujours être suivi par lot (traçabilité).",
#     )
#     duree_conservation_jours = models.PositiveIntegerField(
#         "Durée de conservation (jours)", null=True, blank=True,
#         help_text="Sert à calculer la DLC/DDM d'un lot à sa date de fabrication. Laisser vide si non périssable.",
#     )
#     stock_minimum = models.DecimalField(
#         "Stock minimum", max_digits=14, decimal_places=3, default=0,
#         help_text="Seuil déclenchant une alerte de rupture.",
#     )
#     stock_alerte = models.DecimalField(
#         "Stock d'alerte", max_digits=14, decimal_places=3, default=0,
#         help_text="Seuil d'alerte précoce, avant la rupture (stock_minimum).",
#     )
#     emplacement_stockage = models.CharField(
#         "Emplacement de stockage par défaut", max_length=100, blank=True,
#     )

#     # --- Bloc 9 : Comptabilité & analytique ---
#     compte_vente = models.CharField(
#         "Compte de vente (comptabilité)", max_length=30, blank=True,
#         help_text="Ex : 701200 - utilisé pour l'export vers Sage 100.",
#     )
#     activite_analytique = models.CharField("Activité analytique", max_length=100, blank=True)
#     centre_cout = models.CharField("Centre de coût", max_length=100, blank=True)

#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Article"
#         verbose_name_plural = "Articles"
#         ordering = ["code"]

#     def __str__(self):
#         return f"{self.code} - {self.designation}"

#     @property
#     def peut_etre_facture(self):
#         """
#         Un article sans code fiscal ne doit jamais pouvoir être vendu
#         (règle du document : le vendeur ne choisit jamais les taux -
#         s'il n'y a pas de code fiscal, il n'y a pas de taux à
#         appliquer, donc pas de facturation possible). Utilisé par
#         apps/commercial/models.py::Facture avant de générer une ligne.
#         """
#         return self.code_fiscal is not None and self.code_fiscal.actif


# class StatutFicheTechnique(models.TextChoices):
#     BROUILLON = "BROUILLON", "Brouillon"
#     VALIDEE = "VALIDEE", "Validée"
#     ARCHIVEE = "ARCHIVEE", "Archivée"


# class FicheTechnique(models.Model):
#     """
#     La "recette" d'un article fabriqué : quels intrants, en quelle
#     quantité, pour produire une unité de l'article.

#     Versionnée : chaque nouvelle version d'une fiche technique doit
#     être validée avant utilisation en production. L'historique des
#     versions est conservé (rien n'est supprimé).
#     """
#     article = models.ForeignKey(
#         Article, verbose_name="Article fabriqué",
#         on_delete=models.PROTECT, related_name="fiches_techniques",
#     )
#     version = models.PositiveIntegerField("Version", default=1)
#     statut = models.CharField(
#         "Statut", max_length=20,
#         choices=StatutFicheTechnique.choices,
#         default=StatutFicheTechnique.BROUILLON,
#     )
#     cree_par = models.ForeignKey(
#         Utilisateur, verbose_name="Créée par",
#         on_delete=models.PROTECT, related_name="fiches_creees",
#     )
#     valide_par = models.ForeignKey(
#         Utilisateur, verbose_name="Validée par",
#         on_delete=models.PROTECT, related_name="fiches_validees",
#         null=True, blank=True,
#     )
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)
#     date_validation = models.DateTimeField("Date de validation", null=True, blank=True)

#     class Meta:
#         verbose_name = "Fiche technique"
#         verbose_name_plural = "Fiches techniques"
#         unique_together = ("article", "version")
#         ordering = ["article", "-version"]

#     def __str__(self):
#         return f"Fiche {self.article.code} v{self.version} ({self.get_statut_display()})"

#     def valider(self, utilisateur):
#         """
#         Fait passer la fiche de BROUILLON à VALIDEE.
#         Seule une fiche validée peut être utilisée pour calculer les
#         besoins matières d'un ordre de fabrication (voir apps/production).
#         """
#         if self.statut != StatutFicheTechnique.BROUILLON:
#             raise ValueError("Seule une fiche en brouillon peut être validée.")
#         self.statut = StatutFicheTechnique.VALIDEE
#         self.valide_par = utilisateur
#         from django.utils import timezone
#         self.date_validation = timezone.now()
#         self.save()


# class CompositionFicheTechnique(models.Model):
#     """
#     Une ligne de recette : "il faut X kg/L/unités de telle matière
#     pour produire une unité de l'article de la fiche technique".
#     """
#     fiche_technique = models.ForeignKey(
#         FicheTechnique, verbose_name="Fiche technique",
#         on_delete=models.CASCADE, related_name="composition",
#     )
#     matiere = models.ForeignKey(
#         Article, verbose_name="Matière / intrant",
#         on_delete=models.PROTECT, related_name="utilise_dans_fiches",
#     )
#     quantite_necessaire = models.DecimalField(
#         "Quantité nécessaire par unité produite",
#         max_digits=12, decimal_places=4,
#     )

#     class Meta:
#         verbose_name = "Ligne de composition"
#         verbose_name_plural = "Composition des fiches techniques"
#         unique_together = ("fiche_technique", "matiere")

#     def __str__(self):
#         return f"{self.fiche_technique} : {self.quantite_necessaire} {self.matiere.unite_mesure} de {self.matiere.designation}"


# class FicheConditionnement(models.Model):
#     """
#     Comment un produit fini est emballé pour l'expédition :
#     nombre d'unités par carton, type d'emballage, poids, palettisation.
#     """
#     article = models.ForeignKey(
#         Article, verbose_name="Article", on_delete=models.CASCADE,
#         related_name="fiches_conditionnement",
#     )
#     nombre_unites_par_carton = models.PositiveIntegerField("Unités par carton")
#     type_emballage = models.CharField("Type d'emballage", max_length=100)
#     poids_carton_kg = models.DecimalField(
#         "Poids du carton (kg)", max_digits=8, decimal_places=2,
#         null=True, blank=True,
#     )
#     nombre_cartons_par_palette = models.PositiveIntegerField(
#         "Cartons par palette", null=True, blank=True,
#     )

#     class Meta:
#         verbose_name = "Fiche de conditionnement"
#         verbose_name_plural = "Fiches de conditionnement"

#     def __str__(self):
#         return f"Conditionnement {self.article.code}"


# class MomentControle(models.TextChoices):
#     APRES_TRAITEMENT = "APRES_TRAITEMENT", "Après traitement"
#     AVANT_LIBERATION = "AVANT_LIBERATION", "Avant libération du lot"
#     FIN_DE_LIGNE = "FIN_DE_LIGNE", "Fin de ligne"
#     RECEPTION = "RECEPTION", "À réception"
#     AUTRE = "AUTRE", "Autre"


# class ControleQualiteRequis(models.Model):
#     """
#     Bloc 7 de la fiche article : la LISTE DES CONTRÔLES ATTENDUS pour
#     un produit (ex : pH, microbiologie, aspect emballage), avec le
#     seuil/la norme et le moment où le contrôle doit avoir lieu.

#     À ne pas confondre avec apps.qualite.models.ControleQualite, qui
#     trace le contrôle RÉELLEMENT effectué sur un lot précis. Ce
#     modèle-ci est la définition théorique (paramétrage), l'autre est
#     l'exécution réelle - exactement la même logique que
#     FicheTechnique (théorique) vs SortieMatiere (réel) en production.
#     """
#     article = models.ForeignKey(
#         Article, verbose_name="Article", on_delete=models.CASCADE,
#         related_name="controles_qualite_requis",
#     )
#     type_controle = models.CharField(
#         "Type de contrôle", max_length=100,
#         help_text="Ex : pH, Microbiologie, Aspect/emballage, Brix (taux de sucre)",
#     )
#     norme_ou_seuil = models.CharField(
#         "Norme ou seuil attendu", max_length=200,
#         help_text="Ex : 'Conforme au standard EVAM', 'pH entre 3,5 et 4,2'",
#     )
#     moment = models.CharField(
#         "Moment du contrôle", max_length=20, choices=MomentControle.choices,
#     )
#     obligatoire = models.BooleanField(
#         "Obligatoire avant libération", default=True,
#         help_text="Si coché, le lot ne peut pas être libéré (voir apps.qualite) tant que ce contrôle n'a pas un résultat conforme.",
#     )

#     class Meta:
#         verbose_name = "Contrôle qualité requis"
#         verbose_name_plural = "Contrôles qualité requis (paramétrage)"
#         ordering = ["article", "moment"]

#     def __str__(self):
#         return f"{self.article.code} : {self.type_controle} ({self.get_moment_display()})"


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

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur
from apps.fiscalite.models import CodeFiscal
from apps.core.models import generer_code_unique
from apps.core import codification
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_positif_optionnel,
    valeur_en_base, verifier_transition,
)


class TypeArticle(models.TextChoices):
    """Catégories du Guide du paramétrage (§6)."""
    MATIERE_PREMIERE = "MATIERE_PREMIERE", "Matière première"
    PRODUIT_INTERMEDIAIRE = "PRODUIT_INTERMEDIAIRE", "Produit intermédiaire"
    PRODUIT_FINI = "PRODUIT_FINI", "Produit fini"
    EMBALLAGE = "EMBALLAGE", "Emballage"
    CONSOMMABLE = "CONSOMMABLE", "Consommable"
    FLUIDE_PROCESS = "FLUIDE_PROCESS", "Fluide de process"


# Articles achetés et consommés, jamais fabriqués par un OF.
TYPES_NON_FABRIQUES = (TypeArticle.MATIERE_PREMIERE, TypeArticle.EMBALLAGE, TypeArticle.CONSOMMABLE)
# Articles pouvant entrer dans une composition (recette / conditionnement).
TYPES_COMPOSANTS = (
    TypeArticle.MATIERE_PREMIERE, TypeArticle.PRODUIT_INTERMEDIAIRE, TypeArticle.EMBALLAGE,
    TypeArticle.CONSOMMABLE, TypeArticle.FLUIDE_PROCESS,
)


class UniteMesure(models.TextChoices):
    KILOGRAMME = "KG", "Kilogramme"
    GRAMME = "G", "Gramme"
    LITRE = "L", "Litre"
    CENTILITRE = "CL", "Centilitre"
    METRE_CUBE = "M3", "Mètre cube"
    UNITE = "UNITE", "Unité"
    BOUTEILLE = "BOUTEILLE", "Bouteille"
    POT = "POT", "Pot"
    PACK = "PACK", "Pack"
    CARTON = "CARTON", "Carton"
    SAC = "SAC", "Sac"
    PALETTE = "PALETTE", "Palette"
    METRE = "M", "Mètre"


# Conversions universelles (valables pour tout article). Les conversions
# propres à un article (1 sac de sucre = 25 kg, 1 carton = 6 bouteilles)
# sont paramétrées dans ConversionUnite.
CONVERSIONS_STANDARD = {
    ("KG", "G"): 1000,
    ("L", "CL"): 100,
    ("M3", "L"): 1000,
}


class ModeApprovisionnement(models.TextChoices):
    ACHETE = "ACHETE", "Acheté"
    FABRIQUE = "FABRIQUE", "Fabriqué"
    PROCESS = "PROCESS", "Produit par le process"


class FamilleArticle(models.Model):
    """
    Liste déroulante des familles de produits/matières (§1 de la fiche
    article : "Eau", "Jus", "Yaourt"...). Table de paramétrage, pas un
    choix figé dans le code : l'Administrateur SI peut en ajouter une
    nouvelle depuis l'admin sans redéploiement (voir la commande
    initialiser_referentiel_valeurs pour les valeurs de départ connues).
    """
    nom = models.CharField("Famille", max_length=50, unique=True)
    activite = models.ForeignKey(
        "industriel.Activite", verbose_name="Activité", on_delete=models.PROTECT,
        null=True, blank=True, related_name="familles",
        help_text="Les produits finis de cette famille appartiennent à cette activité (Eau -> EAU...).",
    )
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Famille d'article"
        verbose_name_plural = "Familles d'article"
        ordering = ["nom"]

    def __str__(self):
        return self.nom

    def save(self, *args, **kwargs):
        """Rattachement automatique à l'activité de même nom (famille « Jus » -> activité JUS)."""
        if self.activite_id is None and self.nom:
            from apps.industriel.models import Activite
            try:
                sigle = codification.sigle(self.nom)
            except ValueError:
                sigle = None
            self.activite = (
                Activite.objects.filter(designation__iexact=self.nom.strip()).first()
                or (Activite.objects.filter(code__startswith=sigle).first() if sigle else None)
            )
        super().save(*args, **kwargs)


class FormatArticle(models.Model):
    """Liste déroulante des formats connus (70 cl, 100 cl, 125 g...)."""
    valeur = models.CharField("Format", max_length=30, unique=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Format d'article"
        verbose_name_plural = "Formats d'article"
        ordering = ["valeur"]

    def __str__(self):
        return self.valeur


class Parfum(models.Model):
    """Liste déroulante des parfums/variantes connus (Nature, Grenadine, Fraise...)."""
    nom = models.CharField("Parfum / variante", max_length=50, unique=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Parfum / variante"
        verbose_name_plural = "Parfums / variantes"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class UniteVenteArticle(models.Model):
    """Liste déroulante des unités de vente connues (Pack de 8, Carton de 12, Pot...)."""
    nom = models.CharField("Unité de vente", max_length=50, unique=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Unité de vente"
        verbose_name_plural = "Unités de vente"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


# Préfixe du code article automatique, selon le type.
PREFIXES_CODE_ARTICLE = {
    TypeArticle.MATIERE_PREMIERE: "MP",
    TypeArticle.PRODUIT_INTERMEDIAIRE: "PI",
    TypeArticle.PRODUIT_FINI: "PF",
    TypeArticle.EMBALLAGE: "EMB",
    TypeArticle.CONSOMMABLE: "CONS",
    TypeArticle.FLUIDE_PROCESS: "FLU",
}


def _nombre(texte):
    """Premier nombre d'un libellé (« 1,5 L » -> Decimal('1.5')), ou None."""
    import re
    from decimal import Decimal
    trouve = re.search(r"\d+(?:[.,]\d+)?", texte or "")
    return Decimal(trouve.group().replace(",", ".")) if trouve else None


def contenance_depuis_format(valeur):
    """« 70 cl » -> (0.7, 'L') ; « 1,5 L » -> (1.5, 'L') ; « 125 g » -> (0.125, 'KG') ; sinon (None, '')."""
    from decimal import Decimal
    nombre = _nombre(valeur)
    if nombre is None:
        return None, ""
    unite = codification._ascii_majuscules(valeur).replace(" ", "")
    if "CL" in unite:
        return nombre / Decimal(100), "L"
    if "ML" in unite:
        return nombre / Decimal(1000), "L"
    if "KG" in unite:
        return nombre, "KG"
    if unite.endswith("G") or "G" in unite.replace("KG", ""):
        return nombre / Decimal(1000), "KG"
    if "L" in unite:
        return nombre, "L"
    return None, ""


class Article(ValidationAvantEnregistrement, models.Model):
    """
    Toute chose qui peut être achetée, stockée, produite ou vendue :
    matière première (ex: préforme, arôme), produit intermédiaire
    (ex: bouteille soufflée, étiquette) ou produit fini (ex: EAU 100cl).

    Fiche maître du produit (voir "Proposition de fiche article EVAM") :
    regroupe les paramètres de production, stock, qualité, commercial,
    fiscalité et comptabilité analytique, pour que chaque module les
    réutilise sans ressaisie (règle fondamentale du cahier des charges,
    §15 : "une information saisie ne doit pas être ressaisie ailleurs").
    """
    # --- Bloc 1 : Identité du produit ---
    code = models.CharField(
        "Code article", max_length=30, unique=True, editable=False,
        help_text="Généré automatiquement, jamais saisi. Produit fini : famille + parfum + "
                  "format + unité de vente (ex : EAU70P8, JUSGRE70P8). Matière première / "
                  "produit intermédiaire : MP-000001 / PI-000001.",
    )
    designation = models.CharField(
        "Désignation", max_length=200, blank=True,
        help_text="Laisser vide pour la générer automatiquement à partir de la famille, "
                   "du parfum, du format et de l'unité de vente choisis.",
    )
    type_article = models.CharField(
        "Type d'article", max_length=30, choices=TypeArticle.choices
    )
    famille = models.ForeignKey(
        FamilleArticle, verbose_name="Famille", on_delete=models.PROTECT,
        null=True, blank=True, related_name="articles",
        help_text="Choisie dans la liste (Eau, Jus, Yaourt...) - plus de saisie libre.",
    )
    sous_famille = models.CharField(
        "Sous-famille", max_length=50, blank=True,
        help_text="Reste en saisie libre : aucune liste fixe connue pour ce niveau à ce jour.",
    )
    marque = models.CharField("Marque", max_length=50, blank=True, default="EVAM")
    format = models.ForeignKey(
        FormatArticle, verbose_name="Format", on_delete=models.PROTECT,
        null=True, blank=True, related_name="articles",
        help_text="Choisi dans la liste (70 cl, 100 cl, 125 g...).",
    )
    parfum = models.ForeignKey(
        Parfum, verbose_name="Parfum / variante", on_delete=models.PROTECT,
        null=True, blank=True, related_name="articles",
        help_text="Choisi dans la liste (Nature, Grenadine, Fraise...) - vide si non applicable.",
    )
    unite_mesure = models.CharField(
        "Unité de base", max_length=10, choices=UniteMesure.choices,
        help_text="Unité de gestion interne (ex : Unité pour une bouteille).",
    )
    unite_vente = models.ForeignKey(
        UniteVenteArticle, verbose_name="Unité de vente", on_delete=models.PROTECT,
        null=True, blank=True, related_name="articles",
        help_text="Choisie dans la liste (Pack de 8, Carton de 12...) - l'unité réellement facturée au client.",
    )
    actif = models.BooleanField("Actif", default=True)

    # --- Socle industriel (Guide du paramétrage §6 à §8) ---
    activite = models.ForeignKey(
        "industriel.Activite", verbose_name="Activité", on_delete=models.PROTECT,
        null=True, blank=True, related_name="produits",
        help_text="Produit fini : déduite de la famille (Eau -> EAU). Sert aux lignes, circuits, contrôles et coûts.",
    )
    activites_autorisees = models.ManyToManyField(
        "industriel.Activite", verbose_name="Activités autorisées", blank=True, related_name="articles_autorises",
        help_text="Un même article (ex : sucre) sert plusieurs activités : on ne le duplique pas. Vide = toutes.",
    )
    mode_approvisionnement = models.CharField(
        "Mode d'approvisionnement", max_length=10, choices=ModeApprovisionnement.choices, blank=True,
        help_text="Déduit du type si vide : acheté (MP, emballage, consommable), fabriqué (produit fini...).",
    )
    unite_achat = models.CharField(
        "Unité d'achat", max_length=10, choices=UniteMesure.choices, blank=True,
        help_text="Ex : sac (1 sac = 25 kg, voir les conversions). Vide = unité de base.",
    )
    unite_consommation = models.CharField(
        "Unité de consommation", max_length=10, choices=UniteMesure.choices, blank=True,
        help_text="Unité des recettes et des sorties vers la production. Vide = unité de base.",
    )
    contenance = models.DecimalField(
        "Contenance / poids unitaire", max_digits=10, decimal_places=4, null=True, blank=True,
        help_text="Produit fini : contenu d'une bouteille/pot (0,7 L ; 0,125 kg). Déduit du format si vide.",
    )
    unite_contenance = models.CharField(
        "Unité de contenance", max_length=10, choices=[("L", "Litre"), ("KG", "Kilogramme")], blank=True,
    )
    unites_par_pack = models.PositiveIntegerField(
        "Unités par pack", null=True, blank=True,
        help_text="Bouteilles/pots par pack ou carton (Pack de 6 -> 6). Déduit de l'unité de vente si vide.",
    )
    unites_par_unite_stock = models.PositiveIntegerField(
        "Unités (bouteilles/pots) par unité de stock", null=True, blank=True,
        help_text="1 si le stock et les OF comptent des bouteilles ; 6 s'ils comptent des packs de 6. "
                  "Déduit de l'unité de base si vide (Pack/Carton -> unités par pack, sinon 1).",
    )
    packs_par_palette = models.PositiveIntegerField("Packs par palette", null=True, blank=True)
    type_emballage = models.CharField(
        "Type d'emballage", max_length=100, blank=True,
        help_text="Ex : bouteille PET soufflée sur site, pot, film, carton.",
    )

    # --- Bloc 2 : Fiscalité ---
    # Volontairement une simple FK, jamais un taux en clair sur
    # l'article : le vendeur ne doit jamais pouvoir modifier un taux
    # à la volée (règle du document fiscal). Nullable pour ne pas
    # bloquer la création d'un article en attendant son rattachement
    # fiscal, mais voir Article.peut_etre_facture ci-dessous : un
    # article sans code fiscal ne doit pas pouvoir être facturé.
    code_fiscal = models.ForeignKey(
        CodeFiscal, verbose_name="Code fiscal", on_delete=models.PROTECT,
        null=True, blank=True, related_name="articles",
        help_text="Détermine automatiquement la TVA, l'accise et les centimes additionnels appliqués à la facturation.",
    )

    # --- Bloc 6 : Stock & traçabilité ---
    suivi_par_lot = models.BooleanField(
        "Suivi par lot", default=True,
        help_text="Un produit fabriqué doit presque toujours être suivi par lot (traçabilité).",
    )
    duree_conservation_jours = models.PositiveIntegerField(
        "Durée de conservation (jours)", null=True, blank=True,
        help_text="Sert à calculer la DLC/DDM d'un lot à sa date de fabrication. Laisser vide si non périssable.",
    )
    stock_minimum = models.DecimalField(
        "Stock minimum", max_digits=14, decimal_places=3, default=0,
        help_text="Seuil déclenchant une alerte de rupture.",
    )
    stock_alerte = models.DecimalField(
        "Stock d'alerte", max_digits=14, decimal_places=3, default=0,
        help_text="Seuil d'alerte précoce, avant la rupture (stock_minimum).",
    )
    emplacement_stockage = models.CharField(
        "Emplacement de stockage par défaut", max_length=100, blank=True,
    )

    # --- Bloc 9 : Comptabilité & analytique ---
    compte_vente = models.CharField(
        "Compte de vente (comptabilité)", max_length=30, blank=True,
        help_text="Ex : 701200 - utilisé pour l'export vers Sage 100.",
    )
    activite_analytique = models.CharField("Activité analytique", max_length=100, blank=True)
    centre_cout = models.CharField("Centre de coût", max_length=100, blank=True)

    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Article"
        verbose_name_plural = "Articles"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    # Champs qui composent le code d'un produit fini : ils ne changent plus
    # une fois l'article utilisé (commande, stock, OF, lot, facture...).
    CHAMPS_CODE = ("type_article", "famille", "parfum", "format", "unite_vente")

    def code_produit_fini_attendu(self):
        return codification.code_produit_fini(
            famille=self.famille.nom, format_valeur=self.format.valeur,
            unite_vente=self.unite_vente.nom, parfum=self.parfum.nom if self.parfum_id else None,
        )

    def est_utilise(self):
        """L'article figure-t-il déjà dans un document (le code est alors figé) ?"""
        if self.pk is None:
            return False
        from apps.commercial.models import LigneCommande, LigneFacture
        from apps.stocks.models import MouvementStock
        from apps.production.models import OrdreFabrication, PlanProduction
        from apps.qualite.models import Lot
        return any(
            modele.objects.filter(article_id=self.pk).exists()
            for modele in (LigneCommande, LigneFacture, MouvementStock, OrdreFabrication, PlanProduction, Lot)
        )

    def champs_code_modifies(self):
        """Champs de codification changés par rapport à la base (un champ vide qu'on complète ne compte pas)."""
        if self.pk is None:
            return []
        modifies = []
        for champ in self.CHAMPS_CODE:
            attribut = champ if champ == "type_article" else f"{champ}_id"
            ancien = valeur_en_base(self, champ)
            if ancien is not None and ancien != getattr(self, attribut):
                modifies.append(champ)
        return modifies

    def completer_donnees_industrielles(self):
        """
        Déduit ce qui est déjà connu, sans ressaisie : activité depuis la
        famille, contenance depuis le format (70 cl -> 0,7 L), unités par
        pack depuis l'unité de vente (Pack de 6 -> 6), mode
        d'approvisionnement depuis le type. Une valeur saisie l'emporte.
        """
        if self.activite_id is None and self.famille_id and self.famille.activite_id \
                and self.type_article == TypeArticle.PRODUIT_FINI:
            self.activite_id = self.famille.activite_id
        if self.contenance is None and self.format_id:
            self.contenance, self.unite_contenance = contenance_depuis_format(self.format.valeur)
        if self.unites_par_pack is None and self.unite_vente_id:
            nombre = _nombre(self.unite_vente.nom)
            self.unites_par_pack = int(nombre) if nombre else 1
        if not self.mode_approvisionnement and self.type_article:
            self.mode_approvisionnement = (
                ModeApprovisionnement.ACHETE if self.type_article in TYPES_NON_FABRIQUES
                else ModeApprovisionnement.PROCESS if self.type_article == TypeArticle.FLUIDE_PROCESS
                else ModeApprovisionnement.FABRIQUE
            )

    # --- Quantités industrielles (clés de répartition des coûts) ---
    @property
    def facteur_unites(self):
        """Nombre de bouteilles/pots dans UNE unité de stock de l'article."""
        from decimal import Decimal
        if self.unites_par_unite_stock:
            return Decimal(self.unites_par_unite_stock)
        if self.unite_mesure in (UniteMesure.PACK, UniteMesure.CARTON) and self.unites_par_pack:
            return Decimal(self.unites_par_pack)
        return Decimal(1)

    def en_unites(self, quantite):
        """Quantité (en unité de stock) -> nombre de bouteilles/pots."""
        from decimal import Decimal
        return Decimal(quantite or 0) * self.facteur_unites

    def en_packs(self, quantite):
        from decimal import Decimal
        return self.en_unites(quantite) / Decimal(self.unites_par_pack or 1)

    def en_contenance(self, quantite):
        """Quantité -> litres (ou kg) de produit ; None si la contenance n'est pas connue."""
        if not self.contenance:
            return None
        return self.en_unites(quantite) * self.contenance

    def en_palettes(self, quantite):
        if not self.packs_par_palette:
            return None
        from decimal import Decimal
        return self.en_packs(quantite) / Decimal(self.packs_par_palette)

    def convertir(self, quantite, de, vers):
        """Conversion centralisée (voir ConversionUnite.convertir)."""
        return ConversionUnite.convertir(quantite, de, vers, article=self)

    def est_autorise_pour(self, activite):
        if activite is None or not self.pk:
            return True
        if self.activite_id:
            return self.activite_id == activite.pk
        return not self.activites_autorisees.exists() or self.activites_autorisees.filter(pk=activite.pk).exists()

    def save(self, *args, **kwargs):
        """
        Code automatique (voir apps/core/codification.py) :
        - produit fini : recalculé depuis famille/parfum/format/unité tant
          que l'article n'est utilisé dans aucun document, figé ensuite ;
        - autres : numéro MP-/PI- attribué à la création.
        Génère aussi la désignation si elle n'est pas fournie, à partir
        des listes déroulantes choisies : "Famille Parfum Format - Unité
        de vente" (ex : "Jus Grenadine 70 cl - Pack de 8"). Évite toute
        saisie libre du nom du produit, conformément au principe
        "valeurs déjà connues, choisies dans des listes".
        """
        modifie = bool(self.champs_code_modifies())
        self.completer_donnees_industrielles()
        if self.type_article == TypeArticle.PRODUIT_FINI:
            if not self.code or not self.est_utilise():
                self.code = self.code_produit_fini_attendu()
        elif not self.code or (modifie and not self.est_utilise()):
            self.code = generer_code_unique(Article, PREFIXES_CODE_ARTICLE.get(self.type_article, "ART"))
        if modifie and not self.est_utilise():
            self.designation = ""
        if not self.designation:
            morceaux = []
            if self.famille_id:
                morceaux.append(self.famille.nom)
            if self.parfum_id:
                morceaux.append(self.parfum.nom)
            if self.format_id:
                morceaux.append(self.format.valeur)
            designation = " ".join(morceaux)
            if self.unite_vente_id:
                designation = f"{designation} - {self.unite_vente.nom}" if designation else self.unite_vente.nom
            self.designation = designation or self.code
        super().save(*args, **kwargs)

    def clean(self):
        """
        Produit fini : famille, format et unité de vente obligatoires (ils
        forment le code) ; parfum obligatoire sauf pour l'eau. Deux produits
        finis identiques ne peuvent pas coexister. Une fois l'article
        utilisé, les champs qui forment le code ne changent plus.
        """
        if self.type_article == TypeArticle.PRODUIT_FINI:
            manquants = {
                champ: "Obligatoire pour un produit fini (sert à former son code)."
                for champ in ("famille", "format", "unite_vente")
                if getattr(self, f"{champ}_id") is None
            }
            if manquants:
                raise ValidationError(manquants)
            if self.parfum_id is None and codification.sigle(self.famille.nom) != "EAU":
                raise ValidationError({"parfum": f"Le parfum est obligatoire pour un produit de la famille « {self.famille.nom} »."})
            try:
                code = self.code_produit_fini_attendu()
            except ValueError as erreur:
                raise ValidationError({"format": str(erreur)})
            doublon = Article.objects.filter(code=code).exclude(pk=self.pk).first()
            if doublon and (self.pk is None or not self.est_utilise()):
                raise ValidationError({"famille": (
                    f"Ce produit existe déjà : {doublon.code} - {doublon.designation}."
                )})
        modifies = self.champs_code_modifies()
        if modifies and self.est_utilise():
            raise ValidationError({modifies[0]: (
                f"L'article {self.code} est déjà utilisé (commande, stock, OF...) : "
                "son type, sa famille, son parfum, son format et son unité de vente ne peuvent plus changer."
            )})
        if self.pk and self.type_article in TYPES_NON_FABRIQUES \
                and valeur_en_base(self, "type_article") not in TYPES_NON_FABRIQUES \
                and self.fiches_techniques.exists():
            raise ValidationError({"type_article": (
                f"Cet article a déjà une fiche de composition : il ne peut pas devenir « {self.get_type_article_display()} »."
            )})
        if self.famille_id and self.famille.activite_id and self.activite_id \
                and self.type_article == TypeArticle.PRODUIT_FINI and self.activite_id != self.famille.activite_id:
            raise ValidationError({"activite": (
                f"La famille « {self.famille.nom} » appartient à l'activité {self.famille.activite.code}."
            )})
        if self.activite_id and self.pk and valeur_en_base(self, "activite") not in (None, self.activite_id) and self.est_utilise():
            raise ValidationError({"activite": "Cet article est déjà utilisé : son activité ne change plus."})
        exiger_positif_optionnel(self.contenance, "contenance", "La contenance", strict=True)
        if self.contenance and not self.unite_contenance:
            raise ValidationError({"unite_contenance": "Précisez l'unité de la contenance (L ou kg)."})
        for champ in ("unites_par_pack", "unites_par_unite_stock", "packs_par_palette"):
            if getattr(self, champ) == 0:
                raise ValidationError({champ: "Cette valeur doit être supérieure à 0 (laisser vide si inconnue)."})
        exiger_positif(self.stock_minimum, "stock_minimum", "Le stock minimum", strict=False)
        exiger_positif(self.stock_alerte, "stock_alerte", "Le stock d'alerte", strict=False)
        if self.code_fiscal_id and not self.code_fiscal.actif and valeur_en_base(self, "code_fiscal") != self.code_fiscal_id:
            raise ValidationError({"code_fiscal": f"Le code fiscal {self.code_fiscal.code} est inactif."})

    def creer_fiche_technique_brouillon(self, utilisateur):
        """
        Un produit fini doit toujours avoir sa fiche de composition :
        dès sa création, une fiche v1 en BROUILLON est créée
        automatiquement, prête à recevoir sa composition (toutes les
        matières premières, emballages... nécessaires pour le fabriquer).
        L'ADMIN_SI la complète puis la valide.
        Ne fait rien si l'article n'est pas un produit fini ou a déjà une fiche.
        """
        if self.type_article != TypeArticle.PRODUIT_FINI or self.fiches_techniques.exists():
            return None
        return FicheTechnique.objects.create(article=self, version=1, cree_par=utilisateur)

    @property
    def fiche_technique_validee(self):
        """
        La recette en vigueur : fiche validée de l'article (version la plus
        récente, dans ses dates de validité), sinon fiche validée d'un autre
        format qui la partage (« une recette n'est pas recréée pour chaque
        format si la composition reste identique »). None sinon.
        """
        from django.db.models import Q
        from django.utils import timezone
        aujourd_hui = timezone.localdate()
        en_vigueur = FicheTechnique.objects.filter(statut=StatutFicheTechnique.VALIDEE).filter(
            Q(date_debut_validite__isnull=True) | Q(date_debut_validite__lte=aujourd_hui),
            Q(date_fin_validite__isnull=True) | Q(date_fin_validite__gte=aujourd_hui),
        )
        return (
            en_vigueur.filter(article_id=self.pk).order_by("-version").first()
            or en_vigueur.filter(formats_associes=self).order_by("-version").first()
        )

    @property
    def peut_etre_facture(self):
        """
        Un article sans code fiscal ne doit jamais pouvoir être vendu
        (règle du document : le vendeur ne choisit jamais les taux -
        s'il n'y a pas de code fiscal, il n'y a pas de taux à
        appliquer, donc pas de facturation possible). Utilisé par
        apps/commercial/models.py::Facture avant de générer une ligne.
        """
        return self.code_fiscal is not None and self.code_fiscal.actif


class StatutFicheTechnique(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    EN_TEST = "EN_TEST", "En test"
    VALIDEE = "VALIDEE", "Validée"
    ARCHIVEE = "ARCHIVEE", "Remplacée / archivée"


class UniteReference(models.TextChoices):
    """Unité de référence d'une recette (« pour 1 000 L », « par unité »...)."""
    UNITE_STOCK = "UNITE_STOCK", "Unité de stock du produit fabriqué"
    LITRE = "L", "Litre de produit"
    KILOGRAMME = "KG", "Kilogramme de produit"


class BaseCalcul(models.TextChoices):
    """Ce à quoi la quantité d'un composant se rapporte."""
    REFERENCE = "REFERENCE", "Quantité de référence de la recette"
    UNITE = "UNITE", "Par bouteille / pot produit"
    PACK = "PACK", "Par pack / carton produit"


class FicheTechnique(ValidationAvantEnregistrement, models.Model):
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

    # --- Recette (Guide §13 et Guide Jus §7) ---
    quantite_reference = models.DecimalField(
        "Quantité de référence", max_digits=12, decimal_places=3, default=1,
        help_text="La composition est donnée pour cette quantité (ex : 1 000 pour « pour 1 000 L »).",
    )
    unite_reference = models.CharField(
        "Unité de référence", max_length=15, choices=UniteReference.choices, default=UniteReference.UNITE_STOCK,
    )
    rendement_theorique_pct = models.DecimalField(
        "Rendement théorique (%)", max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Ex : 98 -> les besoins de la recette sont majorés de 100/98.",
    )
    parametres_process = models.TextField(
        "Paramètres de process", blank=True,
        help_text="Températures, temps, agitation... tels qu'ils figurent sur la fiche validée.",
    )
    formats_associes = models.ManyToManyField(
        Article, verbose_name="Autres formats utilisant cette recette", blank=True, related_name="recettes_partagees",
        help_text="Ex : la recette du jus orange 1 L sert aussi au 70 cl et au 1,5 L (seuls les emballages diffèrent).",
    )
    date_debut_validite = models.DateField("Valide à partir du", null=True, blank=True)
    date_fin_validite = models.DateField("Valide jusqu'au", null=True, blank=True)
    document_reference = models.CharField("Fiche / formulation de référence", max_length=200, blank=True)

    class Meta:
        verbose_name = "Fiche technique"
        verbose_name_plural = "Fiches techniques"
        unique_together = ("article", "version")
        ordering = ["article", "-version"]

    def __str__(self):
        return f"Fiche {self.article.code} v{self.version} ({self.get_statut_display()})"

    TRANSITIONS = {
        StatutFicheTechnique.BROUILLON: {StatutFicheTechnique.EN_TEST, StatutFicheTechnique.VALIDEE},
        StatutFicheTechnique.EN_TEST: {StatutFicheTechnique.BROUILLON, StatutFicheTechnique.VALIDEE},
        StatutFicheTechnique.VALIDEE: {StatutFicheTechnique.ARCHIVEE},
    }
    CHAMPS_RECETTE = (
        "quantite_reference", "unite_reference", "rendement_theorique_pct", "parametres_process",
        "date_debut_validite", "date_fin_validite",
    )

    def clean(self):
        """
        - fiche d'un article fabriqué (pas d'une matière première) ;
        - toujours créée en brouillon ; Brouillon -> (En test) -> Validée -> Remplacée ;
        - une fiche validée ou archivée ne se modifie plus (versionnement :
          on crée une nouvelle version), seul l'archivage est possible.
        """
        if self.article_id and self.article.type_article in TYPES_NON_FABRIQUES:
            raise ValidationError({"article": f"Un article « {self.article.get_type_article_display()} » n'a pas de fiche technique."})
        exiger_positif(self.quantite_reference, "quantite_reference", "La quantité de référence")
        if self.rendement_theorique_pct is not None and not (0 < self.rendement_theorique_pct <= 100):
            raise ValidationError({"rendement_theorique_pct": "Le rendement doit être compris entre 0 (exclu) et 100."})
        if self.date_debut_validite and self.date_fin_validite and self.date_fin_validite < self.date_debut_validite:
            raise ValidationError({"date_fin_validite": "La fin de validité ne peut pas précéder son début."})
        if self.unite_reference in (UniteReference.LITRE, UniteReference.KILOGRAMME) and self.article_id \
                and self.article.contenance and self.article.unite_contenance and self.article.unite_contenance != self.unite_reference:
            raise ValidationError({"unite_reference": (
                f"{self.article.code} se mesure en {self.article.unite_contenance} : la recette ne peut pas être exprimée en {self.unite_reference}."
            )})
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutFicheTechnique.ARCHIVEE:
            raise ValidationError("Cette fiche technique est archivée : elle ne peut plus être modifiée.")
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de la fiche technique",
            initial=StatutFicheTechnique.BROUILLON,
        )
        if ancien_statut in (StatutFicheTechnique.VALIDEE, StatutFicheTechnique.EN_TEST):
            for champ in ("article", "version") + self.CHAMPS_RECETTE:
                attribut = f"{champ}_id" if champ == "article" else champ
                if champ == "date_fin_validite" and ancien_statut == StatutFicheTechnique.VALIDEE:
                    continue   # on peut fixer la fin de validité d'une recette en vigueur
                if valeur_en_base(self, champ) != getattr(self, attribut):
                    raise ValidationError({champ: "Une fiche en test ou validée ne se modifie plus : repassez-la en brouillon ou créez une nouvelle version."})

    def verifier_suppression(self):
        if self.statut != StatutFicheTechnique.BROUILLON:
            raise ValidationError("Une fiche validée ou archivée ne se supprime pas (historique des versions).")

    def elements_disponibles(self):
        """
        Articles pouvant être ajoutés à cette composition, pris dans le
        référentiel : matières premières et produits intermédiaires
        actifs, hors article de la fiche et hors éléments déjà présents.
        """
        return (
            Article.objects.filter(actif=True, type_article__in=TYPES_COMPOSANTS)
            .exclude(pk=self.article_id)
            .exclude(pk__in=self.composition.values("matiere_id"))
            .order_by("type_article", "designation")
        )

    @transaction.atomic
    def ajouter_elements(self, elements):
        """
        Ajoute plusieurs éléments choisis en une fois :
        elements = [{"matiere": <id article>, "quantite_necessaire": ..., "prix_unitaire": ...}, ...]
        Tout ou rien : si un seul élément est invalide (inexistant,
        produit fini, doublon, quantité <= 0, fiche non brouillon...),
        aucun n'est ajouté. Lève ValidationError (message par élément).
        """
        from apps.core.validation import convertir_decimal
        if not isinstance(elements, list) or not elements:
            raise ValidationError({"elements": "Envoyez une liste non vide d'éléments {matiere, quantite_necessaire}."})
        erreurs, lignes = {}, []
        for index, element in enumerate(elements):
            try:
                if not isinstance(element, dict):
                    raise ValidationError("Format attendu : {matiere, quantite_necessaire}.")
                matiere = Article.objects.filter(pk=element.get("matiere")).first()
                if matiere is None:
                    raise ValidationError(f"Article introuvable (id {element.get('matiere')!r}).")
                try:
                    quantite = convertir_decimal(element.get("quantite_necessaire"), "La quantité nécessaire")
                    prix = convertir_decimal(element.get("prix_unitaire"), "Le prix unitaire", strict=False)
                except ValueError as erreur:
                    raise ValidationError(str(erreur))
                optionnels = {
                    champ: element[champ] for champ in ("base_calcul", "ordre_incorporation", "role")
                    if element.get(champ) not in (None, "")
                }
                for champ in ("article_format", "etape"):
                    if element.get(champ) not in (None, ""):
                        optionnels[f"{champ}_id"] = element[champ]
                if element.get("perte_theorique_pct") not in (None, ""):
                    try:
                        optionnels["perte_theorique_pct"] = convertir_decimal(
                            element["perte_theorique_pct"], "La perte théorique", strict=False)
                    except ValueError as erreur:
                        raise ValidationError(str(erreur))
                ligne = CompositionFicheTechnique(
                    fiche_technique=self, matiere=matiere, quantite_necessaire=quantite, prix_unitaire=prix,
                    **optionnels,
                )
                ligne.save()
                lignes.append(ligne)
            except ValidationError as erreur:
                erreurs[f"element_{index + 1}"] = erreur.messages
        if erreurs:
            raise ValidationError(erreurs)
        return lignes

    @transaction.atomic
    def valider(self, utilisateur):
        """
        Fait passer la fiche de BROUILLON à VALIDEE.
        Seule une fiche validée peut être utilisée pour calculer les
        besoins matières d'un ordre de fabrication (voir apps/production).
        Une fiche sans composition ne peut pas être validée, et la
        précédente version validée du même article est archivée (une
        seule version active à la fois).
        """
        if self.statut not in (StatutFicheTechnique.BROUILLON, StatutFicheTechnique.EN_TEST):
            raise ValueError("Seule une fiche en brouillon ou en test peut être validée.")
        if not self.composition.exists():
            raise ValueError("Impossible de valider une fiche technique sans aucune ligne de composition.")
        for ancienne in FicheTechnique.objects.filter(
            article_id=self.article_id, statut=StatutFicheTechnique.VALIDEE,
        ).exclude(pk=self.pk):
            ancienne.statut = StatutFicheTechnique.ARCHIVEE
            ancienne.save()
        self.statut = StatutFicheTechnique.VALIDEE
        self.valide_par = utilisateur
        from django.utils import timezone
        self.date_validation = timezone.now()
        self.save()

    def mettre_en_test(self):
        """Brouillon -> En test (essais avant validation) ; la composition est alors figée."""
        if self.statut != StatutFicheTechnique.BROUILLON:
            raise ValueError("Seule une fiche en brouillon peut passer en test.")
        if not self.composition.exists():
            raise ValueError("Impossible de tester une fiche sans composition.")
        self.statut = StatutFicheTechnique.EN_TEST
        self.save()

    def repasser_en_brouillon(self):
        """En test -> Brouillon (ajustement de la composition après essai)."""
        if self.statut != StatutFicheTechnique.EN_TEST:
            raise ValueError("Seule une fiche en test peut repasser en brouillon.")
        self.statut = StatutFicheTechnique.BROUILLON
        self.save()

    def verifier_formats(self, formats):
        """Formats partageant la recette : produits finis de la même activité, sans recette validée propre."""
        erreurs = []
        for article in formats:
            if article.pk == self.article_id:
                continue
            if article.type_article != TypeArticle.PRODUIT_FINI:
                erreurs.append(f"{article.code} n'est pas un produit fini")
            elif self.article.activite_id and article.activite_id and article.activite_id != self.article.activite_id:
                erreurs.append(f"{article.code} est d'une autre activité")
        if erreurs:
            raise ValidationError({"formats_associes": "; ".join(erreurs) + "."})

    def base_de_calcul(self, article, quantite):
        """Quantité de l'OF exprimée dans l'unité de référence de la recette."""
        from decimal import Decimal
        if self.unite_reference == UniteReference.UNITE_STOCK:
            return Decimal(quantite)
        valeur = article.en_contenance(quantite)
        if valeur is None or article.unite_contenance != self.unite_reference:
            raise ValidationError({"article": (
                f"La recette est exprimée en {self.get_unite_reference_display().lower()} : "
                f"renseignez la contenance de {article.code} (ex : 1 L, 125 g)."
            )})
        return valeur

    def besoins_pour(self, article, quantite):
        """
        Besoins théoriques pour produire `quantite` (unité de stock) de
        `article` : [(ligne de composition, quantité)]. Chaque ligne se
        rapporte à la quantité de référence (majorée du rendement), à la
        bouteille/pot ou au pack ; puis la perte théorique de la ligne
        s'ajoute. Les lignes réservées à un autre format sont ignorées.
        """
        from decimal import Decimal
        resultat = []
        base_reference = None
        for ligne in self.composition.select_related("matiere").order_by("ordre_incorporation", "id"):
            if ligne.article_format_id and ligne.article_format_id != article.pk:
                continue
            if ligne.base_calcul == BaseCalcul.UNITE:
                base = article.en_unites(quantite)
            elif ligne.base_calcul == BaseCalcul.PACK:
                base = article.en_packs(quantite)
            else:
                if base_reference is None:
                    base_reference = self.base_de_calcul(article, quantite) / Decimal(self.quantite_reference)
                    if self.rendement_theorique_pct:
                        base_reference = base_reference * Decimal(100) / Decimal(self.rendement_theorique_pct)
                base = base_reference
            besoin = Decimal(ligne.quantite_necessaire) * base
            if ligne.perte_theorique_pct:
                besoin = besoin * (Decimal(100) + Decimal(ligne.perte_theorique_pct)) / Decimal(100)
            resultat.append((ligne, besoin))
        return resultat


class CompositionFicheTechnique(ValidationAvantEnregistrement, models.Model):
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
        "Quantité nécessaire",
        max_digits=12, decimal_places=4,
        help_text="Pour la quantité de référence de la recette, ou par bouteille/pot ou par pack selon la base de calcul.",
    )
    base_calcul = models.CharField(
        "Base de calcul", max_length=10, choices=BaseCalcul.choices, default=BaseCalcul.REFERENCE,
        help_text="Ingrédients : quantité de référence (ex : 100 kg de sucre pour 1 000 L). "
                  "Emballages : par bouteille (préforme, bouchon) ou par pack (film, carton).",
    )
    article_format = models.ForeignKey(
        Article, verbose_name="Uniquement pour le format", on_delete=models.PROTECT, null=True, blank=True,
        related_name="lignes_composition_specifiques",
        help_text="Recette partagée : emballage propre à un format (préforme 1,5 L...). Vide = tous les formats.",
    )
    ordre_incorporation = models.PositiveIntegerField("Ordre d'incorporation", default=0)
    role = models.CharField("Rôle", max_length=100, blank=True, help_text="Ex : base, ingrédient, emballage primaire.")
    etape = models.ForeignKey(
        "industriel.EtapeStandard", verbose_name="Étape de consommation", on_delete=models.PROTECT,
        null=True, blank=True, related_name="+",
        help_text="Ex : préformes au soufflage, film à la plastification (sert au coût par étape).",
    )
    perte_theorique_pct = models.DecimalField(
        "Perte théorique (%)", max_digits=5, decimal_places=2, null=True, blank=True,
    )
    prix_unitaire = models.DecimalField(
        "Prix unitaire de l'élément", max_digits=14, decimal_places=2, default=0,
        help_text="Prix d'une unité de la matière (ex : 1 000 FCFA le litre de ferment). Sert à chiffrer "
                  "les besoins matières de chaque OF (quantité à produire x quantité nécessaire x prix).",
    )

    class Meta:
        verbose_name = "Ligne de composition"
        verbose_name_plural = "Composition des fiches techniques"
        unique_together = ("fiche_technique", "matiere")

    def __str__(self):
        return f"{self.fiche_technique} : {self.quantite_necessaire} {self.matiere.unite_mesure} de {self.matiere.designation}"

    @property
    def montant_par_unite(self):
        """Coût de cet élément pour UNE unité produite (quantité nécessaire x prix unitaire)."""
        from decimal import Decimal
        return (Decimal(self.quantite_necessaire) * Decimal(self.prix_unitaire)).quantize(Decimal("0.01"))

    def seul_le_prix_change(self):
        """Mise à jour du prix seul : permise même sur une fiche validée (les quantités restent figées)."""
        if self.pk is None:
            return False
        for champ in ("fiche_technique", "matiere", "article_format", "etape"):
            if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                return False
        for champ in ("quantite_necessaire", "base_calcul", "ordre_incorporation", "perte_theorique_pct", "role"):
            if valeur_en_base(self, champ) != getattr(self, champ):
                return False
        return True

    def clean(self):
        """
        La composition (matières, quantités) ne se modifie que tant que la
        fiche est en brouillon. Le PRIX d'un élément peut être mis à jour
        sur une fiche brouillon ou validée : il ne s'applique qu'aux OF
        créés ensuite (les OF existants gardent le prix de leur création).
        """
        exiger_positif(self.quantite_necessaire, "quantite_necessaire", "La quantité nécessaire")
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire", strict=False)
        from apps.core.validation import exiger_pourcentage
        exiger_pourcentage(self.perte_theorique_pct, "perte_theorique_pct", "La perte théorique")
        if self.article_format_id and self.fiche_technique_id:
            fiche = self.fiche_technique
            if self.article_format_id != fiche.article_id and not (
                fiche.pk and fiche.formats_associes.filter(pk=self.article_format_id).exists()
            ):
                raise ValidationError({"article_format": (
                    f"{self.article_format.code} n'utilise pas cette recette : ajoutez-le d'abord aux formats associés."
                )})
        mise_a_jour_prix = self.seul_le_prix_change()
        if mise_a_jour_prix and self.fiche_technique.statut == StatutFicheTechnique.ARCHIVEE:
            raise ValidationError("Cette fiche technique est archivée : ses prix ne se modifient plus.")
        if self.pk and not mise_a_jour_prix:
            ancienne_fiche = FicheTechnique.objects.filter(pk=valeur_en_base(self, "fiche_technique")).first()
            if ancienne_fiche and ancienne_fiche.statut != StatutFicheTechnique.BROUILLON:
                raise ValidationError("Cette fiche technique n'est plus en brouillon : sa composition est figée (seul le prix peut être mis à jour).")
        if self.fiche_technique_id and not mise_a_jour_prix:
            fiche = self.fiche_technique
            if fiche.statut != StatutFicheTechnique.BROUILLON:
                raise ValidationError({"fiche_technique": (
                    "Cette fiche technique n'est plus en brouillon : sa composition est figée "
                    "(créez une nouvelle version)."
                )})
            if self.matiere_id and self.matiere_id == fiche.article_id:
                raise ValidationError({"matiere": "Un article ne peut pas entrer dans sa propre composition."})
            if self.matiere_id and CompositionFicheTechnique.objects.filter(
                fiche_technique_id=fiche.pk, matiere_id=self.matiere_id,
            ).exclude(pk=self.pk).exists():
                raise ValidationError({"matiere": f"{self.matiere.code} figure déjà dans cette composition : modifiez sa quantité."})
        if self.matiere_id:
            if not self.matiere.actif:
                raise ValidationError({"matiere": f"La matière {self.matiere.code} est inactive."})
            if self.matiere.type_article not in TYPES_COMPOSANTS:
                raise ValidationError({"matiere": (
                    f"{self.matiere.code} est un produit fini : la composition ne contient que des "
                    "matières premières, emballages, consommables, fluides de process et produits intermédiaires."
                )})
            if self.fiche_technique_id and self.fiche_technique.article.activite_id \
                    and not self.matiere.est_autorise_pour(self.fiche_technique.article.activite):
                raise ValidationError({"matiere": (
                    f"{self.matiere.code} n'est pas autorisé pour l'activité {self.fiche_technique.article.activite.code}."
                )})

    def verifier_suppression(self):
        if self.fiche_technique.statut != StatutFicheTechnique.BROUILLON:
            raise ValidationError("Cette fiche technique n'est plus en brouillon : sa composition est figée.")


class FicheConditionnement(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        exiger_positif(self.nombre_unites_par_carton, "nombre_unites_par_carton", "Le nombre d'unités par carton")
        exiger_positif_optionnel(self.poids_carton_kg, "poids_carton_kg", "Le poids du carton", strict=True)
        exiger_positif_optionnel(self.nombre_cartons_par_palette, "nombre_cartons_par_palette", "Le nombre de cartons par palette", strict=True)


class MomentControle(models.TextChoices):
    APRES_TRAITEMENT = "APRES_TRAITEMENT", "Après traitement"
    AVANT_LIBERATION = "AVANT_LIBERATION", "Avant libération du lot"
    FIN_DE_LIGNE = "FIN_DE_LIGNE", "Fin de ligne"
    RECEPTION = "RECEPTION", "À réception"
    AUTRE = "AUTRE", "Autre"


class ControleQualiteRequis(models.Model):
    """
    Bloc 7 de la fiche article : la LISTE DES CONTRÔLES ATTENDUS pour
    un produit (ex : pH, microbiologie, aspect emballage), avec le
    seuil/la norme et le moment où le contrôle doit avoir lieu.

    À ne pas confondre avec apps.qualite.models.ControleQualite, qui
    trace le contrôle RÉELLEMENT effectué sur un lot précis. Ce
    modèle-ci est la définition théorique (paramétrage), l'autre est
    l'exécution réelle - exactement la même logique que
    FicheTechnique (théorique) vs SortieMatiere (réel) en production.
    """
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.CASCADE,
        related_name="controles_qualite_requis",
    )
    type_controle = models.CharField(
        "Type de contrôle", max_length=100,
        help_text="Ex : pH, Microbiologie, Aspect/emballage, Brix (taux de sucre)",
    )
    norme_ou_seuil = models.CharField(
        "Norme ou seuil attendu", max_length=200,
        help_text="Ex : 'Conforme au standard EVAM', 'pH entre 3,5 et 4,2'",
    )
    moment = models.CharField(
        "Moment du contrôle", max_length=20, choices=MomentControle.choices,
    )
    obligatoire = models.BooleanField(
        "Obligatoire avant libération", default=True,
        help_text="Si coché, le lot ne peut pas être libéré (voir apps.qualite) tant que ce contrôle n'a pas un résultat conforme.",
    )

    class Meta:
        verbose_name = "Contrôle qualité requis"
        verbose_name_plural = "Contrôles qualité requis (paramétrage)"
        ordering = ["article", "moment"]

    def __str__(self):
        return f"{self.article.code} : {self.type_controle} ({self.get_moment_display()})"


class ConversionUnite(ValidationAvantEnregistrement, models.Model):
    """
    Conversions centralisées (Guide §7 : « il ne faut pas coder une
    conversion différente dans chaque module ») :
        1 SAC = 25 KG (sucre), 1 CARTON = 6 BOUTEILLE, 1 M3 = 1 000 L.
    Sans article : conversion valable pour tous les articles.
    """
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.CASCADE, null=True, blank=True,
        related_name="conversions", help_text="Vide = conversion générale.",
    )
    unite_source = models.CharField("1 unité de", max_length=10, choices=UniteMesure.choices)
    facteur = models.DecimalField("vaut", max_digits=16, decimal_places=6)
    unite_cible = models.CharField("unités de", max_length=10, choices=UniteMesure.choices)

    class Meta:
        verbose_name = "Conversion d'unités"
        verbose_name_plural = "Conversions d'unités"
        unique_together = ("article", "unite_source", "unite_cible")

    def __str__(self):
        cible = f" ({self.article.code})" if self.article_id else ""
        return f"1 {self.unite_source} = {self.facteur} {self.unite_cible}{cible}"

    def clean(self):
        exiger_positif(self.facteur, "facteur", "Le facteur de conversion")
        if self.unite_source == self.unite_cible:
            raise ValidationError({"unite_cible": "Les deux unités doivent être différentes."})
        if ConversionUnite.objects.filter(
            article_id=self.article_id, unite_source=self.unite_cible, unite_cible=self.unite_source,
        ).exclude(pk=self.pk).exists():
            raise ValidationError({"unite_source": "La conversion inverse existe déjà : elle est utilisée dans les deux sens."})

    @staticmethod
    def facteur_entre(de, vers, article=None):
        """Facteur f tel que 1 `de` = f `vers` (Decimal), ou None si aucune conversion n'est connue."""
        from decimal import Decimal
        if de == vers:
            return Decimal(1)
        aretes = {}

        def ajouter(source, cible, facteur):
            facteur = Decimal(facteur)
            aretes.setdefault(source, []).append((cible, facteur))
            aretes.setdefault(cible, []).append((source, Decimal(1) / facteur))

        for (source, cible), facteur in CONVERSIONS_STANDARD.items():
            ajouter(source, cible, facteur)
        conversions = ConversionUnite.objects.filter(article__isnull=True)
        if article is not None and article.pk:
            conversions = ConversionUnite.objects.filter(models.Q(article__isnull=True) | models.Q(article=article))
        for conversion in conversions:
            ajouter(conversion.unite_source, conversion.unite_cible, conversion.facteur)
        # Parcours en largeur : 1 SAC -> 25 KG -> 25 000 G.
        vus, file = {de: Decimal(1)}, [de]
        while file:
            courant = file.pop(0)
            for cible, facteur in aretes.get(courant, []):
                if cible not in vus:
                    vus[cible] = vus[courant] * facteur
                    if cible == vers:
                        return vus[cible]
                    file.append(cible)
        return None

    @classmethod
    def convertir(cls, quantite, de, vers, article=None):
        """Convertit une quantité ; lève ValidationError si aucune conversion n'est paramétrée."""
        from decimal import Decimal
        facteur = cls.facteur_entre(de, vers, article)
        if facteur is None:
            nom = f" pour {article.code}" if article is not None else ""
            raise ValidationError(f"Aucune conversion paramétrée de {de} vers {vers}{nom}.")
        return Decimal(quantite) * facteur
