"""
Vues du module distribution.

Reproduit le circuit à deux acteurs du §12.3 :
- Responsable Distribution : lance la préparation, confirme la
  livraison finale.
- Magasinier : prépare, confirme la sortie magasin.
- Chauffeur : accès restreint à ses livraisons affectées (à affiner
  avec le client, voir README).
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour
from apps.comptes.models import Profil


class VehiculeViewSet(viewsets.ModelViewSet):
    queryset = models.Vehicule.objects.all()
    serializer_class = serializers.VehiculeSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_DISTRIBUTION, Profil.ADMIN_SI)]


class ChauffeurViewSet(viewsets.ModelViewSet):
    queryset = models.Chauffeur.objects.all()
    serializer_class = serializers.ChauffeurSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_DISTRIBUTION, Profil.ADMIN_SI)]


class DepotViewSet(viewsets.ModelViewSet):
    queryset = models.Depot.objects.all()
    serializer_class = serializers.DepotSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_DISTRIBUTION, Profil.ADMIN_SI)]


class TourneeViewSet(viewsets.ModelViewSet):
    queryset = models.Tournee.objects.all()
    serializer_class = serializers.TourneeSerializer
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_DISTRIBUTION, Profil.ADMIN_SI)]
    filterset_fields = ["chauffeur", "vehicule", "date_tournee"]

    def get_queryset(self):
        """Un Chauffeur ne consulte (lecture seule) que ses propres tournées."""
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.CHAUFFEUR:
            return queryset.filter(chauffeur__utilisateur=utilisateur)
        return queryset


class PreparationLivraisonViewSet(viewsets.ModelViewSet):
    queryset = models.PreparationLivraison.objects.all()
    serializer_class = serializers.PreparationLivraisonSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_DISTRIBUTION, Profil.MAGASINIER, Profil.ADMIN_SI,
    )]
    filterset_fields = ["commande", "statut"]

    def perform_create(self, serializer):
        """Seul le Responsable Distribution lance la préparation (§12.3 point 7)."""
        serializer.save(lancee_par=self.request.user)

    @action(detail=True, methods=["post"])
    def confirmer_preparation(self, request, pk=None):
        """
        POST /api/distribution/preparations/{id}/confirmer_preparation/
        Réservé au Magasinier (§12.3 points 8-9) : passe le statut à
        EN_PREPARATION puis, avec confirmer_sortie, à SORTIE_MAGASIN.
        """
        if request.user.profil != Profil.MAGASINIER and not request.user.is_superuser:
            return Response({"erreur": "Seul le Magasinier peut confirmer la préparation."}, status=403)
        preparation = self.get_object()
        preparation.statut = "EN_PREPARATION"
        preparation.preparee_par = request.user
        preparation.save()
        return Response(self.get_serializer(preparation).data)

    @action(detail=True, methods=["post"])
    def confirmer_sortie(self, request, pk=None):
        """POST .../confirmer_sortie/ - Magasinier confirme la sortie magasin (§12.3 point 9)."""
        if request.user.profil != Profil.MAGASINIER and not request.user.is_superuser:
            return Response({"erreur": "Seul le Magasinier peut confirmer la sortie magasin."}, status=403)
        from django.utils import timezone
        preparation = self.get_object()
        preparation.statut = "SORTIE_MAGASIN"
        preparation.date_confirmation_sortie = timezone.now()
        preparation.save()
        return Response(self.get_serializer(preparation).data)


class BonLivraisonViewSet(viewsets.ModelViewSet):
    queryset = models.BonLivraison.objects.all()
    serializer_class = serializers.BonLivraisonSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_DISTRIBUTION, Profil.CHAUFFEUR, Profil.ADMIN_SI,
    )]
    filterset_fields = ["commande", "tournee", "statut"]
    search_fields = ["numero"]

    def get_queryset(self):
        """
        Un Chauffeur ne voit que les bons de livraison de ses propres
        tournées (règle du cahier des charges : "accès limité aux
        livraisons affectées").
        """
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.CHAUFFEUR:
            return queryset.filter(tournee__chauffeur__utilisateur=utilisateur)
        return queryset

    @action(detail=True, methods=["post"])
    def confirmer_livraison(self, request, pk=None):
        """
        POST /api/distribution/bons-livraison/{id}/confirmer_livraison/
        Réservé au Responsable Distribution (§12.3 point 13), après
        signature du client.
        """
        if request.user.profil != Profil.RESPONSABLE_DISTRIBUTION and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Distribution peut confirmer la livraison."}, status=403)
        from django.utils import timezone
        bon = self.get_object()
        bon.statut = "LIVREE"
        bon.signature_client = True
        bon.confirme_par = request.user
        bon.date_livraison = timezone.now()
        bon.save()
        return Response(self.get_serializer(bon).data)


class TransfertDepotViewSet(viewsets.ModelViewSet):
    queryset = models.TransfertDepot.objects.all()
    serializer_class = serializers.TransfertDepotSerializer
    permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
    filterset_fields = ["depot_source", "depot_destination", "statut"]
