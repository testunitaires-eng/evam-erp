"""
Sérialiseurs DRF du module comptes.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class UtilisateurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Utilisateur
        fields = "__all__"


class MatriceDroitSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MatriceDroit
        fields = "__all__"


class JournalActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.JournalAction
        fields = "__all__"

