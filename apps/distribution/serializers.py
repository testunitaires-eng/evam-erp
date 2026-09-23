"""
Sérialiseurs DRF du module distribution.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class VehiculeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Vehicule
        fields = "__all__"


class ChauffeurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Chauffeur
        fields = "__all__"


class DepotSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Depot
        fields = "__all__"


class TourneeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Tournee
        fields = "__all__"


class PreparationLivraisonSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.PreparationLivraison
        fields = "__all__"
        extra_kwargs = {"lancee_par": {"required": False}}
        # Évolution uniquement via /confirmer_preparation/ et /confirmer_sortie/
        # (la sortie magasin mouvemente le stock).
        read_only_fields = ["lancee_par", "statut", "preparee_par", "date_confirmation_sortie"]


class BonLivraisonSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.BonLivraison
        fields = "__all__"
        read_only_fields = ["confirme_par", "date_livraison"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutLivraison.EN_LIVRAISON
        if valeur != actuel and valeur == models.StatutLivraison.LIVREE:
            raise serializers.ValidationError(
                "La livraison est confirmée uniquement par le Responsable Distribution (action /confirmer_livraison/)."
            )
        return valeur


class TransfertDepotSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.TransfertDepot
        fields = "__all__"

