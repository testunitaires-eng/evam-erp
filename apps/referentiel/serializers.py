# """
# Sérialiseurs DRF du module referentiel.

# Chaque sérialiseur expose automatiquement tous les champs de son
# modèle (fields = "__all__") : les libellés visibles dans
# l'API (navigable browsable API de DRF) sont ceux définis en
# verbose_name dans models.py, donc déjà en français.
# """

# from rest_framework import serializers
# from . import models

# class ArticleSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Article
#         fields = "__all__"


# class FicheTechniqueSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.FicheTechnique
#         fields = "__all__"


# class CompositionFicheTechniqueSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.CompositionFicheTechnique
#         fields = "__all__"


# class FicheConditionnementSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.FicheConditionnement
#         fields = "__all__"



"""
Sérialiseurs DRF du module référentiel.
"""

from rest_framework import serializers
from . import models

class ArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Article
        fields = "__all__"


# class FicheTechniqueSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.FicheTechnique
#         fields = "__all__"

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