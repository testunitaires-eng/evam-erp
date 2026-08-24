"""
Vues du module production.

Contient les actions les plus importantes du workflow métier :
- OrdreFabricationViewSet.avancer_statut : fait progresser l'OF dans
  son workflow officiel et calcule automatiquement les besoins matières
  au passage à "Lancé".
- SortieMatiereViewSet : impose le motif obligatoire pour les sorties
  complémentaires et exige la validation du Responsable Production.

Le Responsable Production crée le plan et lance les OF ; l'Agent
Production a un accès plus restreint (seulement ses OF affectés,
saisie de quantités/temps/pertes/incidents) — cette restriction fine
("uniquement les OF qui lui sont affectés") est un point à affiner
avec le client (ajout probable d'un champ agents_affectes sur OF, ou
d'un filtre côté queryset ici).
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError
from . import models, serializers
from apps.comptes.permissions import role_required
from apps.comptes.models import Profil


class PlanProductionViewSet(viewsets.ModelViewSet):
    queryset = models.PlanProduction.objects.all()
    serializer_class = serializers.PlanProductionSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
    filterset_fields = ["article", "statut", "priorite"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class OrdreFabricationViewSet(viewsets.ModelViewSet):
    queryset = models.OrdreFabrication.objects.all()
    serializer_class = serializers.OrdreFabricationSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
    filterset_fields = ["article", "statut"]
    search_fields = ["numero"]

    def get_queryset(self):
        """
        Un Agent Production ne voit que les OF où il est affecté
        (agents_affectes), conformément au cahier des charges.
        Le Responsable Production et l'Administrateur SI voient tout.
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
        Fait passer l'OF à l'étape suivante du workflow officiel
        (Brouillon -> Planifié -> Lancé -> ... -> Clôturé, §8.3).
        Réservé au Responsable Production (l'Agent Production ne peut
        pas faire progresser le workflow, seulement saisir des données
        d'exécution).
        """
        if request.user.profil not in (Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response(
                {"erreur": "Seul le Responsable Production peut faire avancer le statut de l'OF."},
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
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication", "matiere"]


class SortieMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.SortieMatiere.objects.all()
    serializer_class = serializers.SortieMatiereSerializer
    permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
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
    permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
    filterset_fields = ["ordre_fabrication", "matiere"]


class EtapeProductionViewSet(viewsets.ModelViewSet):
    queryset = models.EtapeProduction.objects.all()
    serializer_class = serializers.EtapeProductionSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
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
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
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
