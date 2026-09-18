
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

from django.db import models
from apps.comptes.models import Utilisateur
from apps.fiscalite.models import CodeFiscal


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


class FamilleArticle(models.Model):
    """
    Liste déroulante des familles de produits/matières (§1 de la fiche
    article : "Eau", "Jus", "Yaourt"...). Table de paramétrage, pas un
    choix figé dans le code : l'Administrateur SI peut en ajouter une
    nouvelle depuis l'admin sans redéploiement (voir la commande
    initialiser_referentiel_valeurs pour les valeurs de départ connues).
    """
    nom = models.CharField("Famille", max_length=50, unique=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Famille d'article"
        verbose_name_plural = "Familles d'article"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


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


class Article(models.Model):
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
    code = models.CharField("Code article", max_length=30, unique=True)
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

    def save(self, *args, **kwargs):
        """
        Génère automatiquement la désignation si elle n'est pas fournie,
        à partir des listes déroulantes choisies : "Famille Parfum Format
        - Unité de vente" (ex : "Jus Grenadine 70 cl - Pack de 8"). Évite
        toute saisie libre du nom du produit, conformément au principe
        "valeurs déjà connues, choisies dans des listes".
        """
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