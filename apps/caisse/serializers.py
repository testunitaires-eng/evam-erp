"""
Sérialiseurs DRF du module caisse.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class CaisseSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Caisse
        fields = "__all__"


class SessionCaisseSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SessionCaisse
        fields = "__all__"
        extra_kwargs = {"caissier": {"required": False}}


class EncaissementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Encaissement
        fields = "__all__"


class EcartCaisseSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.EcartCaisse
        fields = "__all__"

