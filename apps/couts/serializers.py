"""
Sérialiseurs DRF du module couts.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class CoutMatiereSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutMatiere
        fields = "__all__"


class CoutEnergieSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutEnergie
        fields = "__all__"


class CoutMainOeuvreSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutMainOeuvre
        fields = "__all__"


class AmortissementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Amortissement
        fields = "__all__"


class CoutStandardSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutStandard
        fields = "__all__"


class CoutReelSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutReel
        fields = "__all__"
        # Calculés par /recalculer/ à partir des données sources, jamais saisis.
        read_only_fields = [
            "cout_matiere_total", "cout_main_oeuvre_total", "cout_energie_total", "cout_amortissement_total",
        ]

