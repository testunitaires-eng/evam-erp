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
from apps.core.views import HistoriqueMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.validation import METHODES_CREATION_LECTURE
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour, acces
from apps.comptes.models import Profil

PROFILS_RECLAMATION = (Profil.RESPONSABLE_DISTRIBUTION, Profil.COMMERCIAL, Profil.ADMIN_SI)
PROFILS_STOCK_QUALITE = (Profil.MAGASINIER, Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI)
PROFILS_RECONDITIONNEMENT = (Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI)


class ReclamationClientViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.ReclamationClient.objects.select_related("retour_physique__controle")
    serializer_class = serializers.ReclamationClientSerializer
    permission_classes = [role_required(*PROFILS_RECLAMATION)]
    filterset_fields = ["client", "statut", "type_probleme", "produit_retourne"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class RetourPhysiqueViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.RetourPhysique.objects.select_related("reclamation__client", "reclamation__article", "lot")
    serializer_class = serializers.RetourPhysiqueSerializer
    permission_classes = [role_required(*PROFILS_STOCK_QUALITE)]
    filterset_fields = ["reclamation", "statut"]
    # Le retour a déjà fait entrer la marchandise en quarantaine : il ne
    # se modifie ni ne se supprime.
    http_method_names = METHODES_CREATION_LECTURE

    def perform_create(self, serializer):
        serializer.save(receptionne_par=self.request.user)

    @action(detail=False, methods=["get"])
    def reclamations_a_receptionner(self, request):
        """
        GET /api/reclamations/retours-physiques/reclamations_a_receptionner/
        Réclamations non clôturées sans retour enregistré : la liste de choix
        du Magasinier à la réception (il ne lit pas les réclamations).
        """
        reclamations = models.ReclamationClient.objects.filter(
            retour_physique__isnull=True,
        ).exclude(statut=models.StatutReclamation.CLOTUREE).select_related(
            "client", "article", "bon_livraison",
        ).order_by("date_creation")
        return Response(serializers.ReclamationAReceptionnerSerializer(reclamations, many=True).data)


class ControleRetourViewSet(viewsets.ModelViewSet):
    queryset = models.ControleRetour.objects.select_related("retour_physique__reclamation__client", "retour_physique__reclamation__article")
    serializer_class = serializers.ControleRetourSerializer
    permission_classes = [role_required(*PROFILS_STOCK_QUALITE)]
    filterset_fields = ["retour_physique", "resultat"]
    # La décision a déjà été appliquée au stock : pas de modification.
    http_method_names = METHODES_CREATION_LECTURE

    def perform_create(self, serializer):
        """
        La décision (réintégration / reconditionnement / rebut) est
        déclenchée automatiquement par ControleRetour.save() -> decider().
        """
        serializer.save(controle_par=self.request.user)


class ReconditionnementViewSet(HistoriqueMixin, viewsets.ModelViewSet):
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
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["reclamation"]


class SolutionClientViewSet(viewsets.ModelViewSet):
    queryset = models.SolutionClient.objects.all()
    serializer_class = serializers.SolutionClientSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.ADMIN_SI)]
    filterset_fields = ["reclamation", "type_solution"]
    # Avoir / décaissement déjà créés, réclamation clôturée : pas de modification.
    http_method_names = METHODES_CREATION_LECTURE

    def perform_create(self, serializer):
        serializer.save(autorise_par=self.request.user)
