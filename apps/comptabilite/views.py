"""Vues du module comptabilité/pilotage - accès transversal en lecture
pour Comptabilité/DAF et Direction, écriture réservée à Comptabilité/
DAF et Administrateur SI."""

from rest_framework import viewsets
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour
from apps.comptes.models import Profil


class AnomalieDetecteeViewSet(viewsets.ModelViewSet):
    queryset = models.AnomalieDetectee.objects.all()
    serializer_class = serializers.AnomalieDetecteeSerializer
    permission_classes = [lecture_seule_pour(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)]
    filterset_fields = ["type_anomalie", "module_source", "statut"]


class ExportComptableViewSet(viewsets.ModelViewSet):
    queryset = models.ExportComptable.objects.all()
    serializer_class = serializers.ExportComptableSerializer
    permission_classes = [role_required(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)]
    filterset_fields = ["type_export"]

    def perform_create(self, serializer):
        serializer.save(genere_par=self.request.user)


class ClotureViewSet(viewsets.ModelViewSet):
    queryset = models.Cloture.objects.all()
    serializer_class = serializers.ClotureSerializer
    permission_classes = [role_required(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)]
    filterset_fields = ["type_cloture", "periode"]

    def perform_create(self, serializer):
        serializer.save(valide_par=self.request.user)
