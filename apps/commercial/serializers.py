"""
Sérialiseurs DRF du module commercial.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Client
        fields = "__all__"


class ProspectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Prospect
        fields = "__all__"


class ContratClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ContratClient
        fields = "__all__"


class TarifSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Tarif
        fields = "__all__"


class CommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Commande
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}


class LigneCommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LigneCommande
        fields = "__all__"


class FactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Facture
        fields = "__all__"

