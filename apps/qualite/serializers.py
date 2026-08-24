"""
Sérialiseurs DRF du module qualite.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class LotSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Lot
        fields = "__all__"


class ControleQualiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ControleQualite
        fields = "__all__"
        extra_kwargs = {"controleur": {"required": False}}

