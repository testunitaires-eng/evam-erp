"""
Sérialiseurs DRF du module qualite.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class LotSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Lot
        fields = "__all__"
        # Le statut évolue uniquement par le contrôle qualité et les
        # actions /liberer/ et /bloquer/ (la libération fait entrer le lot
        # en stock : la contourner donnerait un lot "libéré" hors stock).
        read_only_fields = ["statut"]


class ControleQualiteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ControleQualite
        fields = "__all__"
        extra_kwargs = {"controleur": {"required": False}}
        read_only_fields = ["controleur"]

