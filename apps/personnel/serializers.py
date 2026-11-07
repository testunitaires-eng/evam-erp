"""
Sérialiseurs DRF du module personnel.
"""

from django.utils import timezone
from rest_framework import serializers

from apps.core.serializers import ValidationModeleMixin
from . import models


class OuvrierSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    nom_complet = serializers.CharField(read_only=True)
    sous_contrat = serializers.SerializerMethodField(help_text="Actif et sous contrat aujourd'hui.")
    competences_libelles = serializers.SerializerMethodField()

    class Meta:
        model = models.Ouvrier
        fields = "__all__"

    def get_sous_contrat(self, ouvrier):
        return ouvrier.est_sous_contrat()

    def get_competences_libelles(self, ouvrier):
        return [etape.libelle for etape in ouvrier.competences.all()]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Retirer une compétence : pas d'affectation en cours ou à venir sur cette étape.
        if self.instance is not None and "competences" in attrs:
            gardees = {etape.pk for etape in attrs["competences"]}
            aujourdhui = timezone.localdate()
            for affectation in self.instance.affectations.select_related("etape"):
                if affectation.etape_id not in gardees and (affectation.date_fin is None or affectation.date_fin >= aujourdhui):
                    raise serializers.ValidationError({"competences": (
                        f"« {affectation.etape.libelle} » ne peut pas être retirée : affectation en cours ou à venir ({affectation})."
                    )})
        return attrs


class AffectationSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    ouvrier_nom = serializers.CharField(source="ouvrier.nom_complet", read_only=True)
    ouvrier_matricule = serializers.CharField(source="ouvrier.matricule", read_only=True)
    type_contrat = serializers.CharField(source="ouvrier.type_contrat", read_only=True)
    etape_libelle = serializers.CharField(source="etape.libelle", read_only=True)
    poste_code = serializers.CharField(source="poste.code", read_only=True, default=None)
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True, default=None)

    class Meta:
        model = models.Affectation
        fields = "__all__"
        read_only_fields = ["affecte_par"]
