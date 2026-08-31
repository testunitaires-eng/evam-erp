"""
Sérialiseurs DRF du module comptes.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from . import models

class UtilisateurSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    class Meta:
        model = models.Utilisateur
        fields = "__all__"


    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = models.Utilisateur(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance



class MatriceDroitSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.MatriceDroit
        fields = "__all__"


class JournalActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.JournalAction
        fields = "__all__"

