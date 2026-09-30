"""
Sérialiseurs DRF du module comptabilite.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class AnomalieDetecteeSerializer(serializers.ModelSerializer):
    """Les anomalies sont détectées par le système, jamais saisies : lecture seule."""
    type_libelle = serializers.CharField(source="get_type_anomalie_display", read_only=True)
    statut_libelle = serializers.CharField(source="get_statut_display", read_only=True)
    traite_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = models.AnomalieDetectee
        fields = "__all__"
        read_only_fields = [champ.name for champ in models.AnomalieDetectee._meta.fields]

    def get_traite_par_nom(self, anomalie):
        utilisateur = anomalie.traite_par
        return (utilisateur.get_full_name() or utilisateur.username) if utilisateur else None


class ExportComptableSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ExportComptable
        fields = "__all__"
        extra_kwargs = {"genere_par": {"required": False}}
        read_only_fields = ["genere_par"]


class ClotureSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Cloture
        fields = "__all__"
        extra_kwargs = {"valide_par": {"required": False}}
        read_only_fields = ["valide_par"]



class CompteParametreSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    role = serializers.CharField(source="get_cle_display", read_only=True)

    class Meta:
        model = models.CompteParametre
        fields = ["id", "cle", "role", "numero"]
        read_only_fields = ["cle"]


class LigneEcritureSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LigneEcriture
        fields = ["compte", "compte_tiers", "libelle", "debit", "credit"]


class EcritureComptableSerializer(serializers.ModelSerializer):
    journal_libelle = serializers.CharField(source="get_journal_display", read_only=True)
    lignes = LigneEcritureSerializer(many=True, read_only=True)

    class Meta:
        model = models.EcritureComptable
        fields = ["id", "numero", "journal", "journal_libelle", "date", "piece", "libelle", "exportee_le", "lignes"]


class ParametreControleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    libelle = serializers.CharField(source="get_cle_display", read_only=True)
    minimum = serializers.SerializerMethodField()
    maximum = serializers.SerializerMethodField()
    modifie_par_nom = serializers.SerializerMethodField()

    class Meta:
        model = models.ParametreControle
        fields = ["id", "cle", "libelle", "valeur", "minimum", "maximum", "modifie_par_nom", "date_modification"]
        read_only_fields = ["cle", "date_modification"]

    def get_minimum(self, parametre):
        return models.CONTROLES_PAR_DEFAUT[parametre.cle][1]

    def get_maximum(self, parametre):
        return models.CONTROLES_PAR_DEFAUT[parametre.cle][2]

    def get_modifie_par_nom(self, parametre):
        utilisateur = parametre.modifie_par
        return (utilisateur.get_full_name() or utilisateur.username) if utilisateur else None
