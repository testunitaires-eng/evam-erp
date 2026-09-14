"""
Vues du module stocks.

Droits gérés par la matrice (module STOCKS). Par défaut, le Commercial
a peut_consulter=True mais pas peut_modifier, ce qui reproduit la
règle "consulte le stock disponible mais ne le modifie jamais" - sans
que ce soit figé dans le code : un Administrateur SI peut ajuster ça
depuis la matrice de droits si le besoin métier change.
"""

from rest_framework import viewsets
from . import models, serializers
from apps.comptes.permissions import droit_matrice
from apps.comptes.models import Module


class DepotViewSet(viewsets.ModelViewSet):
    queryset = models.Depot.objects.all()
    serializer_class = serializers.DepotSerializer
    permission_classes = [droit_matrice(Module.STOCKS)]


class StockArticleViewSet(viewsets.ModelViewSet):
    queryset = models.StockArticle.objects.all()
    serializer_class = serializers.StockArticleSerializer
    permission_classes = [droit_matrice(Module.STOCKS)]
    filterset_fields = ["article", "depot"]


class MouvementStockViewSet(viewsets.ModelViewSet):
    queryset = models.MouvementStock.objects.all()
    serializer_class = serializers.MouvementStockSerializer
    permission_classes = [droit_matrice(Module.STOCKS)]
    filterset_fields = ["article", "depot", "type_mouvement"]
    search_fields = ["numero", "document_origine"]

    def perform_create(self, serializer):
        mouvement = serializer.save(utilisateur=self.request.user)
        _appliquer_mouvement_au_stock(mouvement)


def _appliquer_mouvement_au_stock(mouvement):
    """
    Répercute un mouvement sur la quantité physique du StockArticle
    correspondant. ENTREE/RETOUR augmentent le stock, SORTIE le
    diminue, TRANSFERT et AJUSTEMENT sont gérés au cas par cas.
    """
    stock, _ = models.StockArticle.objects.get_or_create(
        article=mouvement.article, depot=mouvement.depot
    )
    if mouvement.type_mouvement in ("ENTREE", "RETOUR", "AJUSTEMENT"):
        stock.quantite_physique += mouvement.quantite
    elif mouvement.type_mouvement == "SORTIE":
        stock.quantite_physique -= mouvement.quantite
    stock.save()


class InventaireViewSet(viewsets.ModelViewSet):
    queryset = models.Inventaire.objects.all()
    serializer_class = serializers.InventaireSerializer
    permission_classes = [droit_matrice(Module.STOCKS)]
    filterset_fields = ["depot", "statut"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class LigneInventaireViewSet(viewsets.ModelViewSet):
    queryset = models.LigneInventaire.objects.all()
    serializer_class = serializers.LigneInventaireSerializer
    permission_classes = [droit_matrice(Module.STOCKS)]
    filterset_fields = ["inventaire", "article"]
