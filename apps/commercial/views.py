"""
Vues du module commercial.

Le Commercial gère prospects/clients/contrats/tarifs/commandes/
factures. Il consulte le stock (module stocks, en lecture) mais ce
module n'expose lui-même aucune écriture sur le stock.
"""

from rest_framework import viewsets
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


class FactureViewSet(viewsets.ModelViewSet):
    queryset = models.Facture.objects.all()
    serializer_class = serializers.FactureSerializer
    permission_classes = [role_required(
        Profil.COMMERCIAL, Profil.CAISSIER, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,
    )]
    filterset_fields = ["client", "statut"]
    search_fields = ["numero"]
