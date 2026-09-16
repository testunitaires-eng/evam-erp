# """
# Sérialiseurs DRF du module production.

# Chaque sérialiseur expose automatiquement tous les champs de son
# modèle (fields = "__all__") : les libellés visibles dans
# l'API (navigable browsable API de DRF) sont ceux définis en
# verbose_name dans models.py, donc déjà en français.
# """

# from rest_framework import serializers
# from . import models

# class PlanProductionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.PlanProduction
#         fields = "__all__"
#         extra_kwargs = {"cree_par": {"required": False}}


# class OrdreFabricationSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.OrdreFabrication
#         fields = "__all__"
#         extra_kwargs = {"responsable": {"required": False}}


# class BesoinMatierePrevuSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.BesoinMatierePrevu
#         fields = "__all__"


# class SortieMatiereSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.SortieMatiere
#         fields = "__all__"


# class RetourMatiereSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.RetourMatiere
#         fields = "__all__"


# class EtapeProductionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.EtapeProduction
#         fields = "__all__"
#         extra_kwargs = {"agent": {"required": False}}


# class PerteProductionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.PerteProduction
#         fields = "__all__"



"""
Sérialiseurs DRF du module production.
"""

from rest_framework import serializers
from . import models

class PlanProductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PlanProduction
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}


class OrdreFabricationSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.OrdreFabrication
        fields = "__all__"
        extra_kwargs = {"responsable": {"required": False}}


class BesoinMatierePrevuSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BesoinMatierePrevu
        fields = "__all__"


class DemandeMatiereSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DemandeMatiere
        fields = "__all__"
        extra_kwargs = {"demandeur": {"required": False}}


class DemandeComplementaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DemandeComplementaire
        fields = "__all__"
        extra_kwargs = {"demandeur": {"required": False}}


class SortieMatiereSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SortieMatiere
        fields = "__all__"


class RetourMatiereSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.RetourMatiere
        fields = "__all__"


class SuiviProductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SuiviProduction
        fields = "__all__"


class SuiviEauSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SuiviEau
        fields = "__all__"


class EtapeProductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.EtapeProduction
        fields = "__all__"
        extra_kwargs = {"agent": {"required": False}}


class PerteProductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PerteProduction
        fields = "__all__"