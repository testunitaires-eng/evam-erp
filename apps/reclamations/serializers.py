"""
Sérialiseurs DRF du module réclamations.
"""

from rest_framework import serializers
from . import models

class ReclamationClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ReclamationClient
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}


class RetourPhysiqueSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.RetourPhysique
        fields = "__all__"
        extra_kwargs = {"receptionne_par": {"required": False}}


class ControleRetourSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ControleRetour
        fields = "__all__"
        extra_kwargs = {"controle_par": {"required": False}}


class ReconditionnementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Reconditionnement
        fields = "__all__"


class CoutRetourPerteSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CoutRetourPerte
        fields = "__all__"


class SolutionClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SolutionClient
        fields = "__all__"
        extra_kwargs = {"autorise_par": {"required": False}}