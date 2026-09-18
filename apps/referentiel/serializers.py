
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
from . import models

class FamilleArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FamilleArticle
        fields = "__all__"


class FormatArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FormatArticle
        fields = "__all__"


class ParfumSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Parfum
        fields = "__all__"


class UniteVenteArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.UniteVenteArticle
        fields = "__all__"


class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Article
        fields = "__all__"


class FicheTechniqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FicheTechnique
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}


class CompositionFicheTechniqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CompositionFicheTechnique
        fields = "__all__"


class FicheConditionnementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FicheConditionnement
        fields = "__all__"


class ControleQualiteRequisSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ControleQualiteRequis
        fields = "__all__"