"""
Vues du module comptabilité/pilotage. Droits gérés par la matrice
(module COMPTABILITE).
"""

from rest_framework import viewsets
from . import models, serializers
from apps.comptes.permissions import droit_matrice
from apps.comptes.models import Module


class AnomalieDetecteeViewSet(viewsets.ModelViewSet):
    queryset = models.AnomalieDetectee.objects.all()
    serializer_class = serializers.AnomalieDetecteeSerializer
    permission_classes = [droit_matrice(Module.COMPTABILITE)]
    filterset_fields = ["type_anomalie", "module_source", "statut"]


class ExportComptableViewSet(viewsets.ModelViewSet):
    """
    Générer un export est une action d'export, pas de création
    classique : "create" est donc mappé sur peut_exporter plutôt que
    peut_creer.
    """
    queryset = models.ExportComptable.objects.all()
    serializer_class = serializers.ExportComptableSerializer
    permission_classes = [droit_matrice(Module.COMPTABILITE, actions_supplementaires={
        "create": "peut_exporter",
    })]
    filterset_fields = ["type_export"]

    def perform_create(self, serializer):
        serializer.save(genere_par=self.request.user)


class ClotureViewSet(viewsets.ModelViewSet):
    queryset = models.Cloture.objects.all()
    serializer_class = serializers.ClotureSerializer
    permission_classes = [droit_matrice(Module.COMPTABILITE)]
    filterset_fields = ["type_cloture", "periode"]

    def perform_create(self, serializer):
        serializer.save(valide_par=self.request.user)
