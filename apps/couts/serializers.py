"""
Sérialiseurs DRF du module couts.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class CoutMatiereSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutMatiere
        fields = "__all__"


class CoutEnergieSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutEnergie
        fields = "__all__"


class CoutMainOeuvreSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutMainOeuvre
        fields = "__all__"


class AmortissementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Amortissement
        fields = "__all__"


class CoutStandardSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutStandard
        fields = "__all__"


class CoutReelSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """Coût de revient complet de l'OF et rentabilité (calculés, lecture seule)."""
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True)
    article = serializers.CharField(source="ordre_fabrication.article.code", read_only=True)
    quantite_produite = serializers.DecimalField(max_digits=16, decimal_places=3, read_only=True)
    cout_total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    cout_unitaire_reel = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True)
    ecart_vs_standard = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True, allow_null=True)
    prix_vente_moyen = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True, allow_null=True)
    marge_unitaire = serializers.DecimalField(max_digits=16, decimal_places=4, read_only=True, allow_null=True)
    taux_marge = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True, allow_null=True)

    class Meta:
        model = models.CoutReel
        fields = "__all__"
        # Calculés par /recalculer/ à partir des données sources, jamais saisis.
        read_only_fields = [
            "cout_matiere_total", "cout_main_oeuvre_total", "cout_energie_total", "cout_amortissement_total",
            "cout_charges_reparties",
        ]



class NatureCoutSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    etape_libelle = serializers.CharField(source="etape.libelle", read_only=True, default=None)

    class Meta:
        model = models.NatureCout
        fields = "__all__"


class ChargeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    nature_libelle = serializers.CharField(source="nature.libelle", read_only=True)
    categorie = serializers.CharField(source="nature.categorie", read_only=True)
    etape = serializers.CharField(source="nature.etape.libelle", read_only=True, default=None)
    inducteur = serializers.CharField(source="nature.inducteur", read_only=True)

    class Meta:
        model = models.Charge
        fields = "__all__"
        read_only_fields = ["saisi_par", "statut_repartition", "motif_non_repartition"]


class RepartitionCoutSerializer(serializers.ModelSerializer):
    charge_numero = serializers.CharField(source="charge.numero", read_only=True)
    activite_code = serializers.CharField(source="activite.code", read_only=True, default=None)
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True, default=None)
    article_code = serializers.CharField(source="article.code", read_only=True, default=None)
    etape_libelle = serializers.CharField(source="etape.libelle", read_only=True, default=None)

    class Meta:
        model = models.RepartitionCout
        fields = "__all__"
