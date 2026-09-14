"""
Vues du module production.

Droits gérés par la matrice (module PRODUCTION). L'accès fin "un
Agent Production ne voit que ses OF affectés" reste géré par
get_queryset() (agents_affectes) : la matrice de droits gère le POUVOIR
FAIRE une action, get_queryset() gère le PÉRIMÈTRE des données visibles
- les deux mécanismes sont complémentaires, pas redondants.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError
from . import models, serializers
from apps.comptes.permissions import droit_matrice, a_le_droit
from apps.comptes.models import Profil, Module


class PlanProductionViewSet(viewsets.ModelViewSet):
    queryset = models.PlanProduction.objects.all()
    serializer_class = serializers.PlanProductionSerializer
    permission_classes = [droit_matrice(Module.PRODUCTION)]
    filterset_fields = ["article", "statut", "priorite"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class OrdreFabricationViewSet(viewsets.ModelViewSet):
    queryset = models.OrdreFabrication.objects.all()
    serializer_class = serializers.OrdreFabricationSerializer
    permission_classes = [droit_matrice(Module.PRODUCTION)]
    filterset_fields = ["article", "statut"]
    search_fields = ["numero"]

    def get_queryset(self):
        """
        Un Agent Production ne voit que les OF où il est affecté
        (agents_affectes), conformément au cahier des charges.
        """
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(agents_affectes=utilisateur)
        return queryset

    def perform_create(self, serializer):
        serializer.save(responsable=self.request.user)

    @action(detail=True, methods=["post"])
    def avancer_statut(self, request, pk=None):
        """
        POST /api/production/ordres-fabrication/{id}/avancer_statut/
        Nécessite peut_valider=True sur le module PRODUCTION (par
        défaut : Responsable Production et Admin SI, pas l'Agent
        Production qui saisit seulement des données d'exécution).
        """
        if not a_le_droit(request.user, Module.PRODUCTION, "peut_valider"):
            return Response(
                {"erreur": "Votre profil ne peut pas faire avancer le statut d'un OF."},
                status=403,
            )
        of = self.get_object()
        try:
            nouveau_statut = of.passer_statut_suivant()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response({"statut": nouveau_statut, "of": self.get_serializer(of).data})


class BesoinMatierePrevuViewSet(viewsets.ReadOnlyModelViewSet):
    """Lecture seule : calculé automatiquement, jamais saisi à la main."""
    queryset = models.BesoinMatierePrevu.objects.all()
    serializer_class = serializers.BesoinMatierePrevuSerializer
    permission_classes = [droit_matrice(Module.PRODUCTION)]
    filterset_fields = ["ordre_fabrication", "matiere"]


class SortieMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.SortieMatiere.objects.all()
    serializer_class = serializers.SortieMatiereSerializer
    permission_classes = [droit_matrice(Module.PRODUCTION)]
    filterset_fields = ["ordre_fabrication", "matiere", "type_sortie"]

    def perform_create(self, serializer):
        """
        Le motif obligatoire pour une sortie complémentaire est vérifié
        par Model.clean() ; on l'appelle explicitement ici car
        ModelSerializer ne l'invoque pas automatiquement.
        """
        instance = serializer.save()
        try:
            instance.clean()
        except DjangoValidationError as erreur:
            instance.delete()
            raise


class RetourMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.RetourMatiere.objects.all()
    serializer_class = serializers.RetourMatiereSerializer
    permission_classes = [droit_matrice(Module.PRODUCTION)]
    filterset_fields = ["ordre_fabrication", "matiere"]


class EtapeProductionViewSet(viewsets.ModelViewSet):
    queryset = models.EtapeProduction.objects.all()
    serializer_class = serializers.EtapeProductionSerializer
    permission_classes = [droit_matrice(Module.PRODUCTION)]
    filterset_fields = ["ordre_fabrication", "etape"]

    def get_queryset(self):
        """Un Agent Production ne voit que les étapes des OF où il est affecté."""
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
        return queryset

    def perform_create(self, serializer):
        serializer.save(agent=self.request.user)


class PerteProductionViewSet(viewsets.ModelViewSet):
    queryset = models.PerteProduction.objects.all()
    serializer_class = serializers.PerteProductionSerializer
    permission_classes = [droit_matrice(Module.PRODUCTION)]
    filterset_fields = ["ordre_fabrication", "motif"]

    def get_queryset(self):
        """Un Agent Production ne voit que les pertes des OF où il est affecté."""
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
        return queryset
