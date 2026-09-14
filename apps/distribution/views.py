"""
Vues du module distribution.

Droits gérés par la matrice (module DISTRIBUTION), avec une nuance
importante : "créer" une préparation (la lancer) et "confirmer" une
préparation/sortie sont deux actions différentes confiées à deux
acteurs différents dans le cahier des charges (§12.3). Comme la
matrice ne connaît que 7 actions génériques, on réutilise peut_modifier
pour la confirmation du Magasinier (distincte de peut_creer, réservé
au Responsable Distribution qui lance la préparation) - voir README,
section limites connues, pour ce compromis.

TransfertDepot est rattaché au module STOCKS (pas DISTRIBUTION) : plus
cohérent avec le rôle du Magasinier, qui gère déjà tous les autres
mouvements de stock sous ce module.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import droit_matrice, a_le_droit
from apps.comptes.models import Module


class VehiculeViewSet(viewsets.ModelViewSet):
    queryset = models.Vehicule.objects.all()
    serializer_class = serializers.VehiculeSerializer
    permission_classes = [droit_matrice(Module.DISTRIBUTION)]


class ChauffeurViewSet(viewsets.ModelViewSet):
    queryset = models.Chauffeur.objects.all()
    serializer_class = serializers.ChauffeurSerializer
    permission_classes = [droit_matrice(Module.DISTRIBUTION)]


class DepotViewSet(viewsets.ModelViewSet):
    queryset = models.Depot.objects.all()
    serializer_class = serializers.DepotSerializer
    permission_classes = [droit_matrice(Module.DISTRIBUTION)]


class TourneeViewSet(viewsets.ModelViewSet):
    queryset = models.Tournee.objects.all()
    serializer_class = serializers.TourneeSerializer
    permission_classes = [droit_matrice(Module.DISTRIBUTION)]
    filterset_fields = ["chauffeur", "vehicule", "date_tournee"]

    def get_queryset(self):
        """Un Chauffeur ne consulte que ses propres tournées."""
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == "CHAUFFEUR":
            return queryset.filter(chauffeur__utilisateur=utilisateur)
        return queryset


class PreparationLivraisonViewSet(viewsets.ModelViewSet):
    queryset = models.PreparationLivraison.objects.all()
    serializer_class = serializers.PreparationLivraisonSerializer
    permission_classes = [droit_matrice(Module.DISTRIBUTION, actions_supplementaires={
        "confirmer_preparation": "peut_modifier", "confirmer_sortie": "peut_modifier",
    })]
    filterset_fields = ["commande", "statut"]

    def perform_create(self, serializer):
        """Seul un profil avec peut_creer sur DISTRIBUTION (par défaut : Responsable Distribution) lance la préparation (§12.3 point 7)."""
        serializer.save(lancee_par=self.request.user)

    @action(detail=True, methods=["post"])
    def confirmer_preparation(self, request, pk=None):
        """POST .../confirmer_preparation/ - nécessite peut_modifier sur DISTRIBUTION (par défaut : Magasinier)."""
        preparation = self.get_object()
        preparation.statut = "EN_PREPARATION"
        preparation.preparee_par = request.user
        preparation.save()
        return Response(self.get_serializer(preparation).data)

    @action(detail=True, methods=["post"])
    def confirmer_sortie(self, request, pk=None):
        """POST .../confirmer_sortie/ - nécessite peut_modifier sur DISTRIBUTION (par défaut : Magasinier)."""
        from django.utils import timezone
        preparation = self.get_object()
        preparation.statut = "SORTIE_MAGASIN"
        preparation.date_confirmation_sortie = timezone.now()
        preparation.save()
        return Response(self.get_serializer(preparation).data)


class BonLivraisonViewSet(viewsets.ModelViewSet):
    queryset = models.BonLivraison.objects.all()
    serializer_class = serializers.BonLivraisonSerializer
    permission_classes = [droit_matrice(Module.DISTRIBUTION)]
    filterset_fields = ["commande", "tournee", "statut"]
    search_fields = ["numero"]

    def get_queryset(self):
        """Un Chauffeur ne voit que les bons de livraison de ses propres tournées."""
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == "CHAUFFEUR":
            return queryset.filter(tournee__chauffeur__utilisateur=utilisateur)
        return queryset

    @action(detail=True, methods=["post"])
    def confirmer_livraison(self, request, pk=None):
        """
        POST /api/distribution/bons-livraison/{id}/confirmer_livraison/
        Action de validation finale : nécessite peut_valider sur
        DISTRIBUTION (par défaut : Responsable Distribution seul).
        """
        if not a_le_droit(request.user, Module.DISTRIBUTION, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas confirmer une livraison."}, status=403)
        from django.utils import timezone
        bon = self.get_object()
        bon.statut = "LIVREE"
        bon.signature_client = True
        bon.confirme_par = request.user
        bon.date_livraison = timezone.now()
        bon.save()
        return Response(self.get_serializer(bon).data)


class TransfertDepotViewSet(viewsets.ModelViewSet):
    """
    Rattaché au module STOCKS (pas DISTRIBUTION) : c'est un mouvement
    de stock entre deux dépôts, cohérent avec les autres droits déjà
    accordés au Magasinier sur ce module.
    """
    queryset = models.TransfertDepot.objects.all()
    serializer_class = serializers.TransfertDepotSerializer
    permission_classes = [droit_matrice(Module.STOCKS)]
    filterset_fields = ["depot_source", "depot_destination", "statut"]
