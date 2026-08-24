"""
Sérialiseurs DRF du module distribution.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class VehiculeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Vehicule
        fields = "__all__"


class ChauffeurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Chauffeur
        fields = "__all__"


class DepotSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Depot
        fields = "__all__"


class TourneeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Tournee
        fields = "__all__"


class PreparationLivraisonSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.PreparationLivraison
        fields = "__all__"
        extra_kwargs = {"lancee_par": {"required": False}}


class BonLivraisonSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BonLivraison
        fields = "__all__"


class TransfertDepotSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.TransfertDepot
        fields = "__all__"

