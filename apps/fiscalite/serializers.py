# """Sérialiseurs DRF du module fiscalité."""

# from rest_framework import serializers
# from . import models


# class CodeFiscalSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.CodeFiscal
#         fields = "__all__"


"""
Sérialiseurs DRF du module fiscalité.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class FamilleFiscaleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.FamilleFiscale
        fields = "__all__"


class CodeFiscalSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CodeFiscal
        fields = "__all__"
