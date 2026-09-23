"""
Vues du module commercial.

Le Commercial gère prospects/clients/contrats/tarifs/commandes/
factures. Il consulte le stock (module stocks, en lecture) mais ce
module n'expose lui-même aucune écriture sur le stock.
"""

from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from . import models, serializers
from apps.comptes.permissions import role_required
from apps.comptes.models import Profil


class ClientViewSet(viewsets.ModelViewSet):
    queryset = models.Client.objects.all()
    serializer_class = serializers.ClientSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF)]
    filterset_fields = ["type_client", "bloque"]
    search_fields = ["code", "nom"]


class ProspectViewSet(viewsets.ModelViewSet):
    queryset = models.Prospect.objects.all()
    serializer_class = serializers.ProspectSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.ADMIN_SI)]
    search_fields = ["nom"]


class ContratClientViewSet(viewsets.ModelViewSet):
    queryset = models.ContratClient.objects.all()
    serializer_class = serializers.ContratClientSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.ADMIN_SI)]
    filterset_fields = ["client"]


class TarifViewSet(viewsets.ModelViewSet):
    queryset = models.Tarif.objects.all()
    serializer_class = serializers.TarifSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.ADMIN_SI)]
    filterset_fields = ["article", "client"]


class CommandeViewSet(viewsets.ModelViewSet):
    queryset = models.Commande.objects.all()
    serializer_class = serializers.CommandeSerializer
    permission_classes = [role_required(
        Profil.COMMERCIAL, Profil.ADMIN_SI, Profil.CAISSIER, Profil.RESPONSABLE_DISTRIBUTION,
    )]
    filterset_fields = ["client", "type_commande", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class LigneCommandeViewSet(viewsets.ModelViewSet):
    queryset = models.LigneCommande.objects.all()
    serializer_class = serializers.LigneCommandeSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.ADMIN_SI)]
    filterset_fields = ["commande", "article"]


# class FactureViewSet(viewsets.ModelViewSet):
#     queryset = models.Facture.objects.all()
#     serializer_class = serializers.FactureSerializer
#     permission_classes = [role_required(
#         Profil.COMMERCIAL, Profil.CAISSIER, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,
#     )]
#     filterset_fields = ["client", "statut"]
#     search_fields = ["numero"]


class FactureViewSet(viewsets.ModelViewSet):
    queryset = models.Facture.objects.all()
    serializer_class = serializers.FactureSerializer
    permission_classes = [role_required(
        Profil.COMMERCIAL, Profil.CAISSIER, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,
    )]
    filterset_fields = ["client", "statut"]
    search_fields = ["numero"]

    @action(detail=True, methods=["post"])
    def generer_lignes(self, request, pk=None):
        """
        POST /api/commercial/factures/{id}/generer_lignes/
        Génère automatiquement les lignes de facture (avec calcul et
        historisation des taxes) à partir des lignes de la commande
        liée. Échoue avec le détail de l'article en cause si un
        article de la commande n'a pas de code fiscal actif.
        """
        facture = self.get_object()
        try:
            facture.generer_lignes_depuis_commande()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(facture).data)




class LigneFactureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture seule : une ligne de facture n'est jamais modifiée après
    coup (elle porte des taux fiscaux figés) - pour corriger une
    erreur, on émet un avoir (à venir), pas une modification directe.
    """
    queryset = models.LigneFacture.objects.all()
    serializer_class = serializers.LigneFactureSerializer
    permission_classes = [role_required(
        Profil.COMMERCIAL, Profil.CAISSIER, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,
    )]
    filterset_fields = ["facture", "article"]





class AvoirViewSet(viewsets.ModelViewSet):
    queryset = models.Avoir.objects.all()
    serializer_class = serializers.AvoirSerializer
    permission_classes = [role_required(Profil.COMMERCIAL, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)]
    filterset_fields = ["client", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def utiliser(self, request, pk=None):
        """POST /api/commercial/avoirs/{id}/utiliser/  Corps : {"facture": <id>}"""
        avoir = self.get_object()
        facture = models.Facture.objects.filter(pk=request.data.get("facture")).first()
        if not facture:
            return Response({"erreur": "Facture introuvable."}, status=400)
        try:
            avoir.utiliser(facture)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(avoir).data)


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def impayes(request):
    """
    GET /api/commercial/impayes/
    §8.5 : factures des clients à crédit non soldées, avec échéance
    dépassée. Filtrable par ?client=<id>.
    """
    factures = models.Facture.objects.exclude(statut="ANNULEE").select_related("client")
    client_filtre = request.query_params.get("client")
    if client_filtre:
        factures = factures.filter(client_id=client_filtre)

    resultat = []
    for facture in factures:
        if facture.est_impayee:
            resultat.append({
                "facture": facture.numero,
                "client": facture.client.nom,
                "echeance": facture.date_echeance,
                "montant": facture.montant_total,
                "paye": facture.montant_paye,
                "restant": facture.solde_restant,
                "jours_retard": facture.jours_retard,
            })
    resultat.sort(key=lambda f: f["jours_retard"], reverse=True)
    return Response(resultat)
