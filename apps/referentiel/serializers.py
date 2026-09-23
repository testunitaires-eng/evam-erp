
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
    class Meta:
        model = models.Article
        fields = "__all__"


class FicheTechniqueSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.FicheTechnique
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        # La validation passe par l'action /valider/ ; via `statut`, seul
        # l'archivage d'une fiche validée est possible.
        read_only_fields = ["cree_par", "valide_par", "date_validation"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutFicheTechnique.BROUILLON
        if valeur != actuel and valeur == models.StatutFicheTechnique.VALIDEE:
            raise serializers.ValidationError("Utilisez l'action /valider/ pour valider une fiche technique.")
        return valeur


class CompositionFicheTechniqueSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CompositionFicheTechnique
        fields = "__all__"


class FicheConditionnementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.FicheConditionnement
        fields = "__all__"


class ControleQualiteRequisSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ControleQualiteRequis
        fields = "__all__"
