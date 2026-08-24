"""
Vues du module stocks.

Le Commercial "consulte le stock disponible mais ne le modifie
jamais" : StockArticle est donc en lecture seule pour tout le monde
sauf Magasinier/Administrateur SI, alors que le Magasinier peut créer
des mouvements (qui mettent StockArticle à jour, voir signals.py).
"""

from rest_framework import viewsets
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour
from apps.comptes.models import Profil


class DepotViewSet(viewsets.ModelViewSet):
    queryset = models.Depot.objects.all()
    serializer_class = serializers.DepotSerializer
    permission_classes = [role_required(Profil.ADMIN_SI, Profil.MAGASINIER)]


class StockArticleViewSet(viewsets.ModelViewSet):
    """
    Lecture ouverte à tous les profils authentifiés (Commercial doit
    pouvoir consulter la disponibilité) ; écriture réservée au
    Magasinier et à l'Administrateur SI.
    """
    queryset = models.StockArticle.objects.all()
    serializer_class = serializers.StockArticleSerializer
    permission_classes = [lecture_seule_pour(Profil.MAGASINIER, Profil.ADMIN_SI)]
    filterset_fields = ["article", "depot"]


class MouvementStockViewSet(viewsets.ModelViewSet):
    queryset = models.MouvementStock.objects.all()
    serializer_class = serializers.MouvementStockSerializer
    permission_classes = [role_required(
        Profil.MAGASINIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF,
    )]
    filterset_fields = ["article", "depot", "type_mouvement"]
    search_fields = ["numero", "document_origine"]

    def perform_create(self, serializer):
        mouvement = serializer.save(utilisateur=self.request.user)
        _appliquer_mouvement_au_stock(mouvement)


def _appliquer_mouvement_au_stock(mouvement):
    """
    Répercute un mouvement sur la quantité physique du StockArticle
    correspondant. ENTREE/RETOUR augmentent le stock, SORTIE le
    diminue, TRANSFERT et AJUSTEMENT sont gérés au cas par cas
    (le transfert crée deux mouvements : une sortie du dépôt source et
    une entrée dans le dépôt destination, à faire au niveau applicatif
    lors de la création du transfert).
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
    permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
    filterset_fields = ["depot", "statut"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class LigneInventaireViewSet(viewsets.ModelViewSet):
    queryset = models.LigneInventaire.objects.all()
    serializer_class = serializers.LigneInventaireSerializer
    permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
    filterset_fields = ["inventaire", "article"]
