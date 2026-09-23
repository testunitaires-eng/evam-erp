"""
Sérialiseurs DRF du module comptabilite.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class AnomalieDetecteeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.AnomalieDetectee
        fields = "__all__"


class ExportComptableSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ExportComptable
        fields = "__all__"
        extra_kwargs = {"genere_par": {"required": False}}
        read_only_fields = ["genere_par"]


class ClotureSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Cloture
        fields = "__all__"
        extra_kwargs = {"valide_par": {"required": False}}
        read_only_fields = ["valide_par"]

