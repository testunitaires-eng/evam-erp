"""
Sérialiseurs DRF du module réclamations.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class ReclamationClientSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ReclamationClient
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        read_only_fields = ["cree_par", "date_cloture", "produit_retourne"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutReclamation.OUVERTE
        if valeur != actuel and valeur == models.StatutReclamation.CLOTUREE:
            raise serializers.ValidationError("Une réclamation est clôturée automatiquement par l'enregistrement de sa solution client.")
        return valeur


class RetourPhysiqueSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.RetourPhysique
        fields = "__all__"
        extra_kwargs = {"receptionne_par": {"required": False}}
        read_only_fields = ["receptionne_par", "statut"]


class ControleRetourSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ControleRetour
        fields = "__all__"
        extra_kwargs = {"controle_par": {"required": False}}
        read_only_fields = ["controle_par"]


class ReconditionnementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Reconditionnement
        fields = "__all__"
        # Renseignés uniquement par l'action /terminer/ (qui réintègre le stock).
        read_only_fields = ["statut", "quantite_reconditionnee", "traite_par", "date_traitement"]


class CoutRetourPerteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutRetourPerte
        fields = "__all__"
        # Remplis automatiquement par le circuit ; seul le coût du produit
        # détruit se valorise manuellement.
        read_only_fields = ["reclamation", "quantite_detruite", "cout_reconditionnement"]


class SolutionClientSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.SolutionClient
        fields = "__all__"
        extra_kwargs = {"autorise_par": {"required": False}}
        read_only_fields = ["autorise_par", "reference_sortie_caisse"]
