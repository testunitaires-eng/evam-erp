
# """
# Sérialiseurs DRF du module référentiel.
# """

# from rest_framework import serializers
# from . import models

# class ArticleSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Article
#         fields = "__all__"


# # class FicheTechniqueSerializer(serializers.ModelSerializer):
# #     class Meta:
# #         model = models.FicheTechnique
# #         fields = "__all__"

# class FicheTechniqueSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.FicheTechnique
#         fields = "__all__"
#         extra_kwargs = {"cree_par": {"required": False}}
        
# class CompositionFicheTechniqueSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.CompositionFicheTechnique
#         fields = "__all__"


# class FicheConditionnementSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.FicheConditionnement
#         fields = "__all__"


# class ControleQualiteRequisSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.ControleQualiteRequis
#         fields = "__all__"



"""
Sérialiseurs DRF du module référentiel.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class FamilleArticleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.FamilleArticle
        fields = "__all__"


class FormatArticleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.FormatArticle
        fields = "__all__"


class ParfumSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Parfum
        fields = "__all__"


class UniteVenteArticleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.UniteVenteArticle
        fields = "__all__"


class ArticleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """
    fiche_technique_brouillon : id de la fiche en cours de paramétrage
    (créée automatiquement pour un produit fini), pour ouvrir
    directement l'écran de composition. fiche_technique_validee : id
    de la fiche en vigueur (celle utilisée par les OF).
    """
    fiche_technique_brouillon = serializers.SerializerMethodField()
    fiche_technique_validee = serializers.SerializerMethodField()
    # Vrai dès que l'article figure dans un document : type, famille,
    # parfum, format et unité de vente sont alors figés (à griser).
    est_verrouille = serializers.SerializerMethodField()

    def get_est_verrouille(self, article):
        return article.est_utilise()

    class Meta:
        model = models.Article
        fields = "__all__"

    def get_fiche_technique_brouillon(self, article):
        fiche = article.fiches_techniques.filter(
            statut=models.StatutFicheTechnique.BROUILLON,
        ).order_by("-version").first()
        return fiche.pk if fiche else None

    def get_fiche_technique_validee(self, article):
        fiche = article.fiche_technique_validee
        return fiche.pk if fiche else None


class ElementCompositionSerializer(serializers.ModelSerializer):
    """
    Un article pouvant entrer dans une composition (matière première ou
    produit intermédiaire actif), tel qu'enregistré en base : sert à
    alimenter la liste de choix, rien n'est ressaisi.
    """
    class Meta:
        model = models.Article
        fields = ["id", "code", "designation", "type_article", "unite_mesure", "unite_consommation"]
        read_only_fields = fields


class CompositionFicheTechniqueSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """
    On choisit l'élément (`matiere` = id d'un article existant) et on
    indique sa quantité par unité produite. Code, désignation, type et
    unité sont repris de la fiche article en base (lecture seule).
    """
    matiere_code = serializers.CharField(source="matiere.code", read_only=True)
    matiere_designation = serializers.CharField(source="matiere.designation", read_only=True)
    matiere_type = serializers.CharField(source="matiere.type_article", read_only=True)
    unite_mesure = serializers.CharField(source="matiere.unite_mesure", read_only=True)
    montant_par_unite = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = models.CompositionFicheTechnique
        fields = "__all__"
        # Chaque élément de la recette doit être chiffré (montant des besoins des OF).
        extra_kwargs = {"prix_unitaire": {"required": True}}


class FicheTechniqueSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    composition = CompositionFicheTechniqueSerializer(many=True, read_only=True)
    # Coût des matières pour UNE unité du produit (somme des éléments).
    cout_matieres_par_unite = serializers.SerializerMethodField()

    def get_cout_matieres_par_unite(self, fiche):
        """Coût matières d'UNE unité de stock du produit (unité de référence, rendement et pertes compris)."""
        from decimal import Decimal
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            besoins = fiche.besoins_pour(fiche.article, 1)
        except DjangoValidationError:
            return None   # recette en litres sans contenance connue
        return sum(((besoin * ligne.prix_unitaire).quantize(Decimal("0.01")) for ligne, besoin in besoins), Decimal(0))

    class Meta:
        model = models.FicheTechnique
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        # La validation passe par l'action /valider/ ; via `statut`, seul
        # l'archivage d'une fiche validée est possible.
        read_only_fields = ["cree_par", "valide_par", "date_validation"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutFicheTechnique.BROUILLON
        if valeur != actuel and valeur in (models.StatutFicheTechnique.VALIDEE, models.StatutFicheTechnique.EN_TEST):
            raise serializers.ValidationError("Utilisez les actions /valider/ ou /mettre_en_test/.")
        return valeur

    def validate(self, attrs):
        attrs = super().validate(attrs)
        formats = attrs.get("formats_associes")
        if formats is not None:
            from django.core.exceptions import ValidationError as DjangoValidationError
            from apps.core.serializers import erreur_django_vers_drf
            fiche = self.instance or models.FicheTechnique(article=attrs.get("article"))
            if self.instance is not None and self.instance.statut != models.StatutFicheTechnique.BROUILLON:
                raise serializers.ValidationError({"formats_associes": "Les formats d'une recette se modifient en brouillon."})
            try:
                fiche.verifier_formats(formats)
            except DjangoValidationError as erreur:
                raise erreur_django_vers_drf(erreur)
        return attrs


class FicheConditionnementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.FicheConditionnement
        fields = "__all__"


class ControleQualiteRequisSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ControleQualiteRequis
        fields = "__all__"


class ConversionUniteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)

    class Meta:
        model = models.ConversionUnite
        fields = "__all__"
