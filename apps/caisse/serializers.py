"""
Sérialiseurs DRF du module caisse.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.comptes.models import Profil
from apps.core.serializers import ValidationModeleMixin
from . import models

class CaisseSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Caisse
        fields = "__all__"


class SessionCaisseSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """Statut et soldes de clôture : uniquement via l'action /cloturer/."""
    class Meta:
        model = models.SessionCaisse
        fields = "__all__"
        extra_kwargs = {"caissier": {"required": False}}
        read_only_fields = [
            "caissier", "statut", "solde_theorique_cloture", "solde_compte_cloture", "date_cloture",
        ]


class EncaissementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Encaissement
        fields = "__all__"

    def validate_session_caisse(self, session):
        """Un caissier n'encaisse que sur SA propre session."""
        utilisateur = self.context["request"].user
        if utilisateur.profil == Profil.CAISSIER and not utilisateur.is_superuser \
                and session.caissier_id != utilisateur.id:
            raise serializers.ValidationError("Vous ne pouvez encaisser que sur votre propre session de caisse.")
        return session


class EcartCaisseSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """Le montant est repris automatiquement de la session ; seule la Comptabilité/DAF valide."""
    class Meta:
        model = models.EcartCaisse
        fields = "__all__"
        read_only_fields = ["montant_ecart"]

    def validate_valide_par(self, valide_par):
        utilisateur = self.context["request"].user
        if valide_par is None:
            return valide_par
        if utilisateur.profil not in (Profil.COMPTABILITE_DAF, Profil.ADMIN_SI) and not utilisateur.is_superuser:
            raise serializers.ValidationError("Seule la Comptabilité/DAF peut valider un écart de caisse.")
        if valide_par.id != utilisateur.id:
            raise serializers.ValidationError("On ne peut valider un écart qu'en son propre nom.")
        return valide_par



class DecaissementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Decaissement
        fields = "__all__"
        extra_kwargs = {"effectue_par": {"required": False}}
        read_only_fields = ["effectue_par"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        utilisateur = self.context["request"].user
        if attrs.get("autorise_par") and attrs["autorise_par"].id == utilisateur.id:
            raise serializers.ValidationError({"autorise_par": (
                "Le décaissement doit être autorisé par une autre personne que celle qui l'effectue."
            )})
        return attrs
