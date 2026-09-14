"""
Vues du module commercial.

Droits gérés par la matrice (module COMMERCIAL). Plusieurs profils
(Commercial, Caissier, Responsable Distribution, Comptabilité/DAF) y
ont des droits différents selon la ressource concernée dans le
cahier des charges - la matrice reste à la granularité du module, pas
de la ressource individuelle (voir README, section limites connues).
"""

from rest_framework import viewsets
from . import models, serializers
from apps.comptes.permissions import droit_matrice
from apps.comptes.models import Module


class ClientViewSet(viewsets.ModelViewSet):
    queryset = models.Client.objects.all()
    serializer_class = serializers.ClientSerializer
    permission_classes = [droit_matrice(Module.COMMERCIAL)]
    filterset_fields = ["type_client", "bloque"]
    search_fields = ["code", "nom"]


class ProspectViewSet(viewsets.ModelViewSet):
    queryset = models.Prospect.objects.all()
    serializer_class = serializers.ProspectSerializer
    permission_classes = [droit_matrice(Module.COMMERCIAL)]
    search_fields = ["nom"]


class ContratClientViewSet(viewsets.ModelViewSet):
    queryset = models.ContratClient.objects.all()
    serializer_class = serializers.ContratClientSerializer
    permission_classes = [droit_matrice(Module.COMMERCIAL)]
    filterset_fields = ["client"]


class TarifViewSet(viewsets.ModelViewSet):
    queryset = models.Tarif.objects.all()
    serializer_class = serializers.TarifSerializer
    permission_classes = [droit_matrice(Module.COMMERCIAL)]
    filterset_fields = ["article", "client"]


class CommandeViewSet(viewsets.ModelViewSet):
    queryset = models.Commande.objects.all()
    serializer_class = serializers.CommandeSerializer
    permission_classes = [droit_matrice(Module.COMMERCIAL)]
    filterset_fields = ["client", "type_commande", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class LigneCommandeViewSet(viewsets.ModelViewSet):
    queryset = models.LigneCommande.objects.all()
    serializer_class = serializers.LigneCommandeSerializer
    permission_classes = [droit_matrice(Module.COMMERCIAL)]
    filterset_fields = ["commande", "article"]


class FactureViewSet(viewsets.ModelViewSet):
    queryset = models.Facture.objects.all()
    serializer_class = serializers.FactureSerializer
    permission_classes = [droit_matrice(Module.COMMERCIAL)]
    filterset_fields = ["client", "statut"]
    search_fields = ["numero"]
