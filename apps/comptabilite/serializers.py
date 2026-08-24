"""
Sérialiseurs DRF du module comptabilite.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class AnomalieDetecteeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.AnomalieDetectee
        fields = "__all__"


class ExportComptableSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ExportComptable
        fields = "__all__"
        extra_kwargs = {"genere_par": {"required": False}}


class ClotureSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Cloture
        fields = "__all__"
        extra_kwargs = {"valide_par": {"required": False}}

