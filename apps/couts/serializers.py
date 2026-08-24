"""
Sérialiseurs DRF du module couts.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class CoutMatiereSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CoutMatiere
        fields = "__all__"


class CoutEnergieSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CoutEnergie
        fields = "__all__"


class CoutMainOeuvreSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CoutMainOeuvre
        fields = "__all__"


class AmortissementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Amortissement
        fields = "__all__"


class CoutStandardSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CoutStandard
        fields = "__all__"


class CoutReelSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CoutReel
        fields = "__all__"

