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
        read_only_fields = ["valeur"]
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


class LotMatiereSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True)
    article_designation = serializers.CharField(source="article.designation", read_only=True)
    depot_nom = serializers.CharField(source="depot.nom", read_only=True)
    # La Qualité ne lit pas les fournisseurs : le nom est porté par le lot.
    fournisseur_nom = serializers.CharField(source="fournisseur.nom", read_only=True, default=None)
    est_perime = serializers.BooleanField(read_only=True)

    class Meta:
        model = models.LotMatiere
        fields = "__all__"
        # Le statut évolue par les actions /liberer/ et /bloquer/ et par les contrôles qualité.
        read_only_fields = ["statut", "ligne_reception"]


class LigneTransfertSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """Ligne libre (article, quantité, lot éventuel) ou palette entière (tout est repris de la palette)."""
    article_code = serializers.CharField(source="article.code", read_only=True)

    class Meta:
        model = models.LigneTransfert
        fields = "__all__"
        extra_kwargs = {"article": {"required": False}, "quantite": {"required": False}}

    def validate(self, attrs):
        palette = attrs.get("palette")
        if palette is not None:
            attrs.update(article=palette.lot.article, lot=palette.lot, quantite=palette.quantite)
        elif self.instance is None:
            manquants = {champ: "Ce champ est obligatoire (ou indiquez une palette)." for champ in ("article", "quantite") if champ not in attrs}
            if manquants:
                raise serializers.ValidationError(manquants)
        return super().validate(attrs)


class TransfertStockSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    lignes = LigneTransfertSerializer(many=True, read_only=True)
    depot_source_nom = serializers.CharField(source="depot_source.nom", read_only=True)
    depot_destination_nom = serializers.CharField(source="depot_destination.nom", read_only=True)

    class Meta:
        model = models.TransfertStock
        fields = "__all__"
        read_only_fields = ["statut", "cree_par", "expedie_par", "recu_par", "date_expedition", "date_reception"]
        extra_kwargs = {"cree_par": {"required": False}}


class EmplacementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    depot_nom = serializers.CharField(source="depot.nom", read_only=True)
    palettes_en_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = models.Emplacement
        fields = "__all__"


class PaletteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    lot_numero = serializers.CharField(source="lot.numero_lot", read_only=True)
    article_code = serializers.CharField(source="lot.article.code", read_only=True)
    depot_nom = serializers.CharField(source="depot.nom", read_only=True)
    emplacement_code = serializers.CharField(source="emplacement.code", read_only=True, default=None)

    class Meta:
        model = models.Palette
        fields = "__all__"
        # Une palette naît de /qualite/lots/{id}/palettiser/ ; on la déplace par /deplacer/.
        read_only_fields = ["lot", "depot", "quantite", "statut", "cree_par", "emplacement"]


class MouvementLotSerializer(serializers.ModelSerializer):
    lot_numero = serializers.CharField(source="lot.numero_lot", read_only=True)
    depot_nom = serializers.CharField(source="depot.nom", read_only=True)

    class Meta:
        model = models.MouvementLot
        fields = "__all__"
