"""
Vues du module réclamations.

Répartition des droits fidèle au croquis :
- ReclamationClient : Module Livraison/Distribution -> Responsable
  Distribution, mais aussi Commercial (qui reçoit souvent l'appel du
  client en premier) et Admin SI.
- RetourPhysique / ControleRetour : Module Stock/Qualité -> Magasinier
  et Responsable Qualité.
- Reconditionnement : Module Production/Stock -> Responsable/Agent
  Production et Magasinier.
- SolutionClient : Module Commercial -> Commercial.
- CoutRetourPerte : Module Coûts -> Comptabilité/DAF, en LECTURE
  (généré automatiquement, jamais saisi directement sauf valorisation
  manuelle du coût produit détruit).
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour
from apps.comptes.models import Profil

PROFILS_RECLAMATION = (Profil.RESPONSABLE_DISTRIBUTION, Profil.COMMERCIAL, Profil.ADMIN_SI)
PROFILS_STOCK_QUALITE = (Profil.MAGASINIER, Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI)
PROFILS_RECONDITIONNEMENT = (Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI)


class ReclamationClientViewSet(viewsets.ModelViewSet):
    queryset = models.ReclamationClient.objects.all()
    serializer_class = serializers.ReclamationClientSerializer
    permission_classes = [role_required(*PROFILS_RECLAMATION)]
    filterset_fields = ["client", "statut", "type_probleme", "produit_retourne"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class RetourPhysiqueViewSet(viewsets.ModelViewSet):
    queryset = models.RetourPhysique.objects.all()
    serializer_class = serializers.RetourPhysiqueSerializer
    permission_classes = [role_required(*PROFILS_STOCK_QUALITE)]
    filterset_fields = ["reclamation", "statut"]

    def perform_create(self, serializer):
        serializer.save(receptionne_par=self.request.user)


class ControleRetourViewSet(viewsets.ModelViewSet):
    queryset = models.ControleRetour.objects.all()
    serializer_class = serializers.ControleRetourSerializer
    permission_classes = [role_required(*PROFILS_STOCK_QUALITE)]
    filterset_fields = ["retour_physique", "resultat"]

    def perform_create(self, serializer):
        """
        La décision (réintégration / reconditionnement / rebut) est
        déclenchée automatiquement par ControleRetour.save() -> decider().
        """
        serializer.save(controle_par=self.request.user)


class ReconditionnementViewSet(viewsets.ModelViewSet):
    queryset = models.Reconditionnement.objects.all()
    serializer_class = serializers.ReconditionnementSerializer
    permission_classes = [role_required(*PROFILS_RECONDITIONNEMENT)]
    filterset_fields = ["controle_retour", "statut"]

    @action(detail=True, methods=["post"])
    def terminer(self, request, pk=None):
        """
        POST /api/reclamations/reconditionnements/{id}/terminer/
        Corps : {"quantite_reconditionnee": ..., "cout": ... (optionnel)}
        Réintègre automatiquement la quantité traitée en stock.
        """
        reconditionnement = self.get_object()
        try:
            reconditionnement.terminer(
                utilisateur=request.user,
                quantite_reconditionnee=request.data.get("quantite_reconditionnee"),
                cout=request.data.get("cout"),
            )
        except (ValueError, TypeError) as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(reconditionnement).data)


class CoutRetourPerteViewSet(viewsets.ModelViewSet):
    """
    Écriture réservée pour la valorisation manuelle du coût produit
    détruit (le reste - quantité, coût reconditionnement - est rempli
    automatiquement par le circuit).
    """
    queryset = models.CoutRetourPerte.objects.all()
    serializer_class = serializers.CoutRetourPerteSerializer
    permission_classes = [lecture_seule_pour(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)]
    filterset_fields = ["reclamation"]


class SolutionClientViewSet(viewsets.ModelViewSet):
    queryset = models.SolutionClient.objects.all()
    serializer_class = serializers.SolutionClientSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.ADMIN_SI)]
    filterset_fields = ["reclamation", "type_solution"]

    def perform_create(self, serializer):
        serializer.save(autorise_par=self.request.user)