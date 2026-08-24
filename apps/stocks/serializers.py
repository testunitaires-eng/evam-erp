"""
Sérialiseurs DRF du module stocks.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class DepotSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Depot
        fields = "__all__"


class StockArticleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.StockArticle
        fields = "__all__"


class MouvementStockSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MouvementStock
        fields = "__all__"
        extra_kwargs = {"utilisateur": {"required": False}}


class InventaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Inventaire
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}


class LigneInventaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LigneInventaire
        fields = "__all__"

