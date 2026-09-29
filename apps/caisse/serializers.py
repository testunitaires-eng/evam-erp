"""
Sérialiseurs DRF du module caisse.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.comptes.models import Profil, Utilisateur
from apps.core.serializers import ValidationModeleMixin
from . import models

class CaisseSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """
    est_principale : caisse de consolidation (créée par le système).
    solde_actuel : pour la principale, le total de toutes les caisses ;
    sinon l'argent de cette caisse. session_ouverte : id ou null.
    """
    est_principale = serializers.BooleanField(read_only=True)
    caissier_nom = serializers.CharField(source="caissier", read_only=True, default=None)
    solde_actuel = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    session_ouverte = serializers.SerializerMethodField()

    class Meta:
        model = models.Caisse
        fields = "__all__"

    def get_session_ouverte(self, caisse):
        session = caisse.session_ouverte()
        return session.pk if session else None


class SessionCaisseSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """
    Ouverture : le caissier n'envoie rien d'obligatoire, sa caisse et le
    solde d'ouverture sont déterminés automatiquement. Statut et soldes
    de clôture : uniquement via l'action /cloturer/.
    """
    solde_theorique_actuel = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    ecart = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = models.SessionCaisse
        fields = "__all__"
        extra_kwargs = {"caissier": {"required": False}, "caisse": {"required": False}}
        read_only_fields = [
            "caissier", "statut", "solde_ouverture", "solde_theorique_cloture",
            "solde_compte_cloture", "date_cloture",
        ]

    def validate(self, attrs):
        if self.instance is None:
            utilisateur = self.context["request"].user
            attrs["caissier"] = utilisateur
            if not attrs.get("caisse"):
                caisse = models.Caisse.objects.filter(caissier=utilisateur).first()
                if caisse is None:
                    raise serializers.ValidationError({"caisse": (
                        "Aucune caisse ne vous est affectée : demandez à l'Administrateur SI de vous en attribuer une."
                    )})
                attrs["caisse"] = caisse
        return super().validate(attrs)


class EncaissementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Encaissement
        fields = "__all__"
        read_only_fields = ["encaisse_par"]

    def validate(self, attrs):
        """Traçabilité : l'encaissement est au nom de l'utilisateur connecté, qui doit être le caissier de la session."""
        attrs["encaisse_par"] = self.context["request"].user
        return super().validate(attrs)


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



class AutorisateurSerializer(serializers.ModelSerializer):
    """Personne pouvant autoriser un décaissement (liste de choix)."""
    nom = serializers.SerializerMethodField()
    profil_libelle = serializers.CharField(source="get_profil_display", read_only=True)

    class Meta:
        model = Utilisateur
        fields = ["id", "username", "nom", "profil", "profil_libelle"]

    def get_nom(self, utilisateur):
        return models.nom_utilisateur(utilisateur)


class DecaissementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    # Liste de choix limitée à la Direction et à la Comptabilité/DAF (comptes actifs).
    autorise_par = serializers.PrimaryKeyRelatedField(
        queryset=Utilisateur.objects.filter(
            profil__in=models.PROFILS_AUTORISANT_DECAISSEMENT, is_active=True,
        ),
        error_messages={"does_not_exist": (
            "Choisissez une personne de la Direction ou de la Comptabilité/DAF "
            "(liste : /api/caisse/decaissements/autorisateurs/)."
        )},
    )
    autorise_par_nom = serializers.SerializerMethodField()
    effectue_par_nom = serializers.SerializerMethodField()

    def get_autorise_par_nom(self, decaissement):
        return models.nom_utilisateur(decaissement.autorise_par)

    def get_effectue_par_nom(self, decaissement):
        return models.nom_utilisateur(decaissement.effectue_par)

    class Meta:
        model = models.Decaissement
        fields = "__all__"
        extra_kwargs = {"effectue_par": {"required": False}}
        read_only_fields = ["effectue_par"]

    def validate(self, attrs):
        utilisateur = self.context["request"].user
        attrs["effectue_par"] = utilisateur
        attrs = super().validate(attrs)
        if attrs.get("autorise_par") and attrs["autorise_par"].id == utilisateur.id:
            raise serializers.ValidationError({"autorise_par": (
                "Le décaissement doit être autorisé par une autre personne que celle qui l'effectue."
            )})
        return attrs
