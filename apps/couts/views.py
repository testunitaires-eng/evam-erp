"""Vues du module coûts - réservé au DAF/Comptabilité et à l'Administrateur SI.
Le Responsable Production ne voit jamais ces données financières
(règle explicite : "ne saisit jamais la valeur financière des matières")."""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required
from apps.comptes.models import Profil

PROFILS_COUTS = (Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI)


class CoutMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.CoutMatiere.objects.all()
    serializer_class = serializers.CoutMatiereSerializer
    permission_classes = [role_required(*PROFILS_COUTS)]
    filterset_fields = ["article"]


class CoutEnergieViewSet(viewsets.ModelViewSet):
    queryset = models.CoutEnergie.objects.all()
    serializer_class = serializers.CoutEnergieSerializer
    permission_classes = [role_required(*PROFILS_COUTS)]
    filterset_fields = ["type_energie", "periode"]


class CoutMainOeuvreViewSet(viewsets.ModelViewSet):
    queryset = models.CoutMainOeuvre.objects.all()
    serializer_class = serializers.CoutMainOeuvreSerializer
    permission_classes = [role_required(*PROFILS_COUTS)]
    filterset_fields = ["ordre_fabrication"]


class AmortissementViewSet(viewsets.ModelViewSet):
    queryset = models.Amortissement.objects.all()
    serializer_class = serializers.AmortissementSerializer
    permission_classes = [role_required(*PROFILS_COUTS)]


class CoutStandardViewSet(viewsets.ModelViewSet):
    queryset = models.CoutStandard.objects.all()
    serializer_class = serializers.CoutStandardSerializer
    permission_classes = [role_required(*PROFILS_COUTS)]
    filterset_fields = ["article"]


class CoutReelViewSet(viewsets.ModelViewSet):
    queryset = models.CoutReel.objects.all()
    serializer_class = serializers.CoutReelSerializer
    permission_classes = [role_required(*PROFILS_COUTS)]
    filterset_fields = ["ordre_fabrication"]

    @action(detail=True, methods=["post"])
    def recalculer(self, request, pk=None):
        """
        POST /api/couts/couts-reels/{id}/recalculer/
        Relance le calcul des 4 composantes du coût réel (voir
        CoutReel.calculer() dans models.py pour le détail de la méthode).
        """
        cout_reel = self.get_object()
        cout_reel.calculer()
        return Response(self.get_serializer(cout_reel).data)
