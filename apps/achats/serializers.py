"""
Sérialiseurs DRF du module achats.
"""

from rest_framework import serializers
from . import models

class FournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Fournisseur
        fields = "__all__"
        extra_kwargs = {"gere_par": {"required": False}}


class ContratFournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ContratFournisseur
        fields = "__all__"
        extra_kwargs = {"gere_par": {"required": False}}


class ArticleFournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ArticleFournisseur
        fields = "__all__"


class BesoinApprovisionnementSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.BesoinApprovisionnement
        fields = "__all__"


class DemandeAchatSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.DemandeAchat
        fields = "__all__"
        extra_kwargs = {"demandeur": {"required": False}}


class CommandeFournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.CommandeFournisseur
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}


class LigneCommandeFournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LigneCommandeFournisseur
        fields = "__all__"


class ReceptionAchatSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ReceptionAchat
        fields = "__all__"
        extra_kwargs = {"receptionne_par": {"required": False}}


class LigneReceptionAchatSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LigneReceptionAchat
        fields = "__all__"


class RetourFournisseurSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.RetourFournisseur
        fields = "__all__"
        extra_kwargs = {"traite_par": {"required": False}}

