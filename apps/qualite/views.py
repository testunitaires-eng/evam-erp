"""
Vues du module qualité.

Droits gérés par la matrice (module QUALITE). Par défaut : Responsable
Qualité peut tout ; Magasinier et Commercial peuvent seulement
consulter (savoir ce qui est vendable/sortable).
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import droit_matrice, a_le_droit
from apps.comptes.models import Module


class LotViewSet(viewsets.ModelViewSet):
    queryset = models.Lot.objects.all()
    serializer_class = serializers.LotSerializer
    permission_classes = [droit_matrice(Module.QUALITE)]
    filterset_fields = ["article", "statut", "ordre_fabrication"]
    search_fields = ["numero_lot"]

    @action(detail=True, methods=["post"])
    def liberer(self, request, pk=None):
        """
        POST /api/qualite/lots/{id}/liberer/
        Nécessite peut_valider=True sur le module QUALITE. Ne
        fonctionne que si le lot est au statut Conforme.
        """
        if not a_le_droit(request.user, Module.QUALITE, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas libérer un lot."}, status=403)
        lot = self.get_object()
        try:
            lot.liberer(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(lot).data)

    @action(detail=True, methods=["post"])
    def bloquer(self, request, pk=None):
        """POST /api/qualite/lots/{id}/bloquer/ - nécessite peut_valider=True sur QUALITE."""
        if not a_le_droit(request.user, Module.QUALITE, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas bloquer un lot."}, status=403)
        lot = self.get_object()
        lot.bloquer(motif=request.data.get("motif", ""))
        return Response(self.get_serializer(lot).data)


class ControleQualiteViewSet(viewsets.ModelViewSet):
    queryset = models.ControleQualite.objects.all()
    serializer_class = serializers.ControleQualiteSerializer
    permission_classes = [droit_matrice(Module.QUALITE)]
    filterset_fields = ["lot", "resultat"]

    def perform_create(self, serializer):
        serializer.save(controleur=self.request.user)
