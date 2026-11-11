from rest_framework import serializers

from apps.core.serializers import ValidationModeleMixin
from . import models


class VersionneeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    figee = serializers.BooleanField(read_only=True)
    saisi_par_nom = serializers.CharField(source="saisi_par.username", read_only=True, default=None)


class ParametresEauSerializer(VersionneeSerializer):
    usine_code = serializers.CharField(source="usine.code", read_only=True)

    class Meta:
        model = models.ParametresEau
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class CaracteristiquesEquipementSerializer(VersionneeSerializer):
    equipement_code = serializers.CharField(source="equipement.code", read_only=True)
    equipement_designation = serializers.CharField(source="equipement.designation", read_only=True)
    bloc = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = models.CaracteristiquesEquipement
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class PrevisionVolumeSerializer(VersionneeSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True)
    volume_m3 = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = models.PrevisionVolume
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class PrevisionCaptageSerializer(VersionneeSerializer):
    part_site_eau = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)

    class Meta:
        model = models.PrevisionCaptage
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class ElementCoutSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    bloc = serializers.CharField(read_only=True, allow_null=True)
    etape_libelle = serializers.CharField(source="etape.libelle", read_only=True)
    equipement_code = serializers.CharField(source="equipement.code", read_only=True, default=None)

    class Meta:
        model = models.ElementCout
        fields = "__all__"


class VersionElementCoutSerializer(VersionneeSerializer):
    element_libelle = serializers.CharField(source="element.libelle", read_only=True)
    famille = serializers.CharField(source="element.famille", read_only=True)

    class Meta:
        model = models.VersionElementCout
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class CoutStandardEauSerializer(serializers.ModelSerializer):
    usine_code = serializers.CharField(source="usine.code", read_only=True)
    cout_litre = serializers.DecimalField(max_digits=14, decimal_places=7, read_only=True)
    propose_par_nom = serializers.CharField(source="propose_par.username", read_only=True, default=None)
    valide_par_nom = serializers.CharField(source="valide_par.username", read_only=True, default=None)

    class Meta:
        model = models.CoutStandardEau
        fields = "__all__"
        read_only_fields = [champ.name for champ in models.CoutStandardEau._meta.fields]
