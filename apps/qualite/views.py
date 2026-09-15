"""
Vues du module qualité.

Seul le Responsable Qualité peut faire passer un lot à LIBERE.
Le Magasinier et le Commercial peuvent CONSULTER les lots (pour savoir
ce qui est vendable/sortable) mais jamais modifier leur statut.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour
from apps.comptes.models import Profil


class LotViewSet(viewsets.ModelViewSet):
    queryset = models.Lot.objects.all()
    serializer_class = serializers.LotSerializer
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI)]
    filterset_fields = ["article", "statut", "ordre_fabrication"]
    search_fields = ["numero_lot"]

    @action(detail=True, methods=["post"])
    def liberer(self, request, pk=None):
        """
        POST /api/qualite/lots/{id}/liberer/
        Réservé au Responsable Qualité. Ne fonctionne que si le lot
        est au statut Conforme.
        """
        if request.user.profil != Profil.RESPONSABLE_QUALITE and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Qualité peut libérer un lot."}, status=403)
        lot = self.get_object()
        try:
            lot.liberer(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(lot).data)

    @action(detail=True, methods=["post"])
    def bloquer(self, request, pk=None):
        """POST /api/qualite/lots/{id}/bloquer/ - réservé au Responsable Qualité."""
        if request.user.profil != Profil.RESPONSABLE_QUALITE and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Qualité peut bloquer un lot."}, status=403)
        lot = self.get_object()
        lot.bloquer(motif=request.data.get("motif", ""))
        return Response(self.get_serializer(lot).data)


class ControleQualiteViewSet(viewsets.ModelViewSet):
    queryset = models.ControleQualite.objects.all()
    serializer_class = serializers.ControleQualiteSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI)]
    filterset_fields = ["lot", "resultat"]

    def perform_create(self, serializer):
        serializer.save(controleur=self.request.user)
