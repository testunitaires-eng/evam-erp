"""
Vues du module coûts. Droits gérés par la matrice (module COUTS).
Par défaut, Comptabilité/DAF a les droits complets, la Direction est
en lecture seule (cohérent avec son rôle de pilotage), et le
Responsable Production n'a aucun droit sur ce module (règle du cahier
des charges : "ne saisit jamais la valeur financière des matières").
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import droit_matrice, a_le_droit
from apps.comptes.models import Module


class CoutMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.CoutMatiere.objects.all()
    serializer_class = serializers.CoutMatiereSerializer
    permission_classes = [droit_matrice(Module.COUTS)]
    filterset_fields = ["article"]


class CoutEnergieViewSet(viewsets.ModelViewSet):
    queryset = models.CoutEnergie.objects.all()
    serializer_class = serializers.CoutEnergieSerializer
    permission_classes = [droit_matrice(Module.COUTS)]
    filterset_fields = ["type_energie", "periode"]


class CoutMainOeuvreViewSet(viewsets.ModelViewSet):
    queryset = models.CoutMainOeuvre.objects.all()
    serializer_class = serializers.CoutMainOeuvreSerializer
    permission_classes = [droit_matrice(Module.COUTS)]
    filterset_fields = ["ordre_fabrication"]


class AmortissementViewSet(viewsets.ModelViewSet):
    queryset = models.Amortissement.objects.all()
    serializer_class = serializers.AmortissementSerializer
    permission_classes = [droit_matrice(Module.COUTS)]


class CoutStandardViewSet(viewsets.ModelViewSet):
    queryset = models.CoutStandard.objects.all()
    serializer_class = serializers.CoutStandardSerializer
    permission_classes = [droit_matrice(Module.COUTS)]
    filterset_fields = ["article"]


class CoutReelViewSet(viewsets.ModelViewSet):
    queryset = models.CoutReel.objects.all()
    serializer_class = serializers.CoutReelSerializer
    permission_classes = [droit_matrice(Module.COUTS)]
    filterset_fields = ["ordre_fabrication"]

    @action(detail=True, methods=["post"])
    def recalculer(self, request, pk=None):
        """POST .../recalculer/ - nécessite peut_valider sur COUTS."""
        if not a_le_droit(request.user, Module.COUTS, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas relancer ce calcul."}, status=403)
        cout_reel = self.get_object()
        cout_reel.calculer()
        return Response(self.get_serializer(cout_reel).data)
