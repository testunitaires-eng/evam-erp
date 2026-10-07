"""Sérialiseurs du socle industriel (codes automatiques en lecture seule)."""

from rest_framework import serializers

from apps.core.serializers import ValidationModeleMixin
from . import models


class ActiviteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Activite
        fields = "__all__"


class UsineSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    activites_codes = serializers.SlugRelatedField(source="activites", slug_field="code", many=True, read_only=True)

    class Meta:
        model = models.Usine
        fields = "__all__"


class EtapeStandardSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    hors_cout_production = serializers.BooleanField(read_only=True)

    class Meta:
        model = models.EtapeStandard
        fields = "__all__"
        extra_kwargs = {"code": {"required": False}}


class AvecFormatsMixin:
    """Contrôle des formats compatibles (produits finis de l'activité de l'objet)."""

    def _verifier_formats(self, attrs, activite):
        formats = attrs.get("formats_compatibles")
        if not formats:
            return
        non_pf = [f.code for f in formats if f.type_article != "PRODUIT_FINI"]
        if non_pf:
            raise serializers.ValidationError({"formats_compatibles": "Seuls des produits finis : " + ", ".join(non_pf) + "."})
        if activite is not None:
            autres = [f.code for f in formats if f.activite_id and f.activite_id != activite.pk]
            if autres:
                raise serializers.ValidationError({"formats_compatibles": f"Formats d'une autre activité que {activite.code} : " + ", ".join(autres) + "."})


class LigneSerializer(AvecFormatsMixin, ValidationModeleMixin, serializers.ModelSerializer):
    usine_code = serializers.CharField(source="usine.code", read_only=True)
    activite_code = serializers.CharField(source="activite.code", read_only=True)

    class Meta:
        model = models.Ligne
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        activite = attrs.get("activite") or (self.instance.activite if self.instance else None)
        self._verifier_formats(attrs, activite)
        return attrs


class PosteSerializer(AvecFormatsMixin, ValidationModeleMixin, serializers.ModelSerializer):
    ligne_code = serializers.CharField(source="ligne.code", read_only=True)
    etape_code = serializers.CharField(source="etape.code", read_only=True)

    class Meta:
        model = models.Poste
        fields = "__all__"
        extra_kwargs = {"designation": {"required": False}}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        ligne = attrs.get("ligne") or (self.instance.ligne if self.instance else None)
        self._verifier_formats(attrs, ligne.activite if ligne else None)
        return attrs


class EquipementSerializer(AvecFormatsMixin, ValidationModeleMixin, serializers.ModelSerializer):
    est_commun = serializers.BooleanField(read_only=True)
    amortissement_mensuel = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True, allow_null=True)

    class Meta:
        model = models.Equipement
        fields = "__all__"

    def validate(self, attrs):
        attrs = super().validate(attrs)
        activite = attrs.get("activite", self.instance.activite if self.instance else None)
        self._verifier_formats(attrs, activite)
        return attrs


class EtapeCircuitSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    etape_code = serializers.CharField(source="etape.code", read_only=True)
    etape_libelle = serializers.CharField(source="etape.libelle", read_only=True)

    class Meta:
        model = models.EtapeCircuit
        fields = "__all__"


class CircuitSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    etapes = EtapeCircuitSerializer(many=True, read_only=True)
    activite_code = serializers.CharField(source="activite.code", read_only=True)

    class Meta:
        model = models.Circuit
        fields = "__all__"
        read_only_fields = ["valide_par", "date_validation", "version"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutCircuit.BROUILLON
        if valeur != actuel and valeur == models.StatutCircuit.VALIDE:
            raise serializers.ValidationError("Utilisez l'action /valider/ pour valider un circuit.")
        return valeur

