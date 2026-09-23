"""
Sérialiseurs DRF du module stocks.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class DepotSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    # Permet au frontend de verrouiller nom/actif et de masquer la
    # suppression pour les dépôts utilisés automatiquement par le code.
    est_systeme = serializers.BooleanField(read_only=True)
    role = serializers.SerializerMethodField()

    class Meta:
        model = models.Depot
        fields = "__all__"

    def get_role(self, depot):
        return models.DEPOTS_SYSTEME.get(depot.nom, "")


class StockArticleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.StockArticle
        fields = "__all__"


class MouvementStockSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.MouvementStock
        fields = "__all__"
        extra_kwargs = {"utilisateur": {"required": False}}


class InventaireSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Inventaire
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}


class LigneInventaireSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.LigneInventaire
        fields = "__all__"

