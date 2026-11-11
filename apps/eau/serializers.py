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
