"""
Sérialiseurs DRF du module achats.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class FournisseurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Fournisseur
        fields = "__all__"
        extra_kwargs = {"gere_par": {"required": False}}


class ContratFournisseurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ContratFournisseur
        fields = "__all__"
        extra_kwargs = {"gere_par": {"required": False}}


class ArticleFournisseurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ArticleFournisseur
        fields = "__all__"


class BesoinApprovisionnementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.BesoinApprovisionnement
        fields = "__all__"


class DemandeAchatSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.DemandeAchat
        fields = "__all__"
        extra_kwargs = {"demandeur": {"required": False}}
        # Traitement uniquement via /approuver/ et /rejeter/ ; "Transformée"
        # est posé automatiquement à la création de la commande fournisseur.
        read_only_fields = ["demandeur", "statut", "approuve_par", "date_traitement"]


class CommandeFournisseurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CommandeFournisseur
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        read_only_fields = ["cree_par"]

    def validate_statut(self, valeur):
        """Envoi via /envoyer/, réception via les lignes de réception ; ici seule l'annulation est possible."""
        actuel = self.instance.statut if self.instance is not None else models.StatutCommandeFournisseur.BROUILLON
        if valeur != actuel and valeur != models.StatutCommandeFournisseur.ANNULEE:
            raise serializers.ValidationError(
                "Utilisez /envoyer/ pour envoyer la commande ; les statuts de réception sont automatiques. "
                "Seule l'annulation (ANNULEE) peut être demandée ici."
            )
        return valeur


class LigneCommandeFournisseurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.LigneCommandeFournisseur
        fields = "__all__"
        # Mise à jour uniquement par les lignes de réception.
        read_only_fields = ["quantite_recue"]


class ReceptionAchatSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ReceptionAchat
        fields = "__all__"
        extra_kwargs = {"receptionne_par": {"required": False}}
        read_only_fields = ["receptionne_par"]


class LigneReceptionAchatSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.LigneReceptionAchat
        fields = "__all__"


class RetourFournisseurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.RetourFournisseur
        fields = "__all__"
        extra_kwargs = {"traite_par": {"required": False}}
        read_only_fields = ["traite_par"]

