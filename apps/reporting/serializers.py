"""Sérialiseurs DRF du module reporting."""

from rest_framework import serializers
from . import models


class RapportGenereSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.RapportGenere
        fields = "__all__"
        extra_kwargs = {"genere_par": {"required": False}}