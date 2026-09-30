# """
# Vues du module stocks.

# Le Commercial "consulte le stock disponible mais ne le modifie
# jamais" : StockArticle est donc en lecture seule pour tout le monde
# sauf Magasinier/Administrateur SI, alors que le Magasinier peut créer
# des mouvements (qui mettent StockArticle à jour, voir signals.py).
# """

# from rest_framework import viewsets
# from . import models, serializers
# from apps.comptes.permissions import role_required, lecture_seule_pour
# from apps.comptes.models import Profil


# # class DepotViewSet(viewsets.ModelViewSet):
# #     queryset = models.Depot.objects.all()
# #     serializer_class = serializers.DepotSerializer
# #     permission_classes = [role_required(Profil.ADMIN_SI, Profil.MAGASINIER)]

# class DepotViewSet(viewsets.ModelViewSet):
#     queryset = models.Depot.objects.all()
#     serializer_class = serializers.DepotSerializer
#     permission_classes = [lecture_seule_pour(Profil.ADMIN_SI, Profil.MAGASINIER)]
    
# class StockArticleViewSet(viewsets.ModelViewSet):
#     """
#     Lecture ouverte à tous les profils authentifiés (Commercial doit
#     pouvoir consulter la disponibilité) ; écriture réservée au
#     Magasinier et à l'Administrateur SI.
#     """
#     queryset = models.StockArticle.objects.all()
#     serializer_class = serializers.StockArticleSerializer
#     permission_classes = [lecture_seule_pour(Profil.MAGASINIER, Profil.ADMIN_SI)]
#     filterset_fields = ["article", "depot"]


# class MouvementStockViewSet(viewsets.ModelViewSet):
#     queryset = models.MouvementStock.objects.all()
#     serializer_class = serializers.MouvementStockSerializer
#     permission_classes = [role_required(
#         Profil.MAGASINIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF,
#     )]
#     # filterset_fields = ["article", "depot", "type_mouvement"]
#     filterset_fields = ["article", "depot", "type_mouvement", "document_origine"]
#     search_fields = ["numero", "document_origine"]

#     def perform_create(self, serializer):
#         mouvement = serializer.save(utilisateur=self.request.user)
#         _appliquer_mouvement_au_stock(mouvement)


# def _appliquer_mouvement_au_stock(mouvement):
#     """
#     Répercute un mouvement sur la quantité physique du StockArticle
#     correspondant. ENTREE/RETOUR augmentent le stock, SORTIE le
#     diminue, TRANSFERT et AJUSTEMENT sont gérés au cas par cas.
#     """
#     stock, _ = models.StockArticle.objects.get_or_create(
#         article=mouvement.article, depot=mouvement.depot
#     )
#     if mouvement.type_mouvement in ("ENTREE", "RETOUR", "AJUSTEMENT"):
#         stock.quantite_physique += mouvement.quantite
#     elif mouvement.type_mouvement == "SORTIE":
#         stock.quantite_physique -= mouvement.quantite
#     stock.save()


# class InventaireViewSet(viewsets.ModelViewSet):
#     queryset = models.Inventaire.objects.all()
#     serializer_class = serializers.InventaireSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
#     filterset_fields = ["depot", "statut"]

#     def perform_create(self, serializer):
#         serializer.save(cree_par=self.request.user)


# class LigneInventaireViewSet(viewsets.ModelViewSet):
#     queryset = models.LigneInventaire.objects.all()
#     serializer_class = serializers.LigneInventaireSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
#     filterset_fields = ["inventaire", "article"]



"""
Vues du module stocks.

Le Commercial "consulte le stock disponible mais ne le modifie
jamais" : StockArticle est donc en lecture seule pour tout le monde
sauf Magasinier/Administrateur SI, alors que le Magasinier peut créer
des mouvements (qui mettent StockArticle à jour, voir signals.py).
"""

from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from apps.core.views import HistoriqueMixin
from . import models, serializers
from apps.core.validation import METHODES_CREATION_LECTURE
from apps.comptes.permissions import role_required, lecture_seule_pour, acces
from apps.comptes.models import Profil


# class DepotViewSet(viewsets.ModelViewSet):
#     queryset = models.Depot.objects.all()
#     serializer_class = serializers.DepotSerializer
#     permission_classes = [role_required(Profil.ADMIN_SI, Profil.MAGASINIER)]

class DepotViewSet(viewsets.ModelViewSet):
    queryset = models.Depot.objects.all()
    serializer_class = serializers.DepotSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_QUALITE, Profil.RESPONSABLE_ACHATS, Profil.COMMERCIAL, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.ADMIN_SI, Profil.MAGASINIER,),
    )]
    
class StockArticleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture seule pour tous les profils authentifiés (Commercial doit
    pouvoir consulter la disponibilité). Le stock n'est JAMAIS modifié
    directement : toute variation passe par un MouvementStock
    (traçabilité, §16.1), qui met StockArticle à jour via signals.py.
    """
    queryset = models.StockArticle.objects.all()
    serializer_class = serializers.StockArticleSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_QUALITE, Profil.RESPONSABLE_ACHATS, Profil.COMMERCIAL, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMPTABILITE_DAF, Profil.MAGASINIER, Profil.ADMIN_SI,),
        ecriture=(),
    )]
    filterset_fields = ["article", "depot"]


class MouvementStockViewSet(viewsets.ModelViewSet):
    queryset = models.MouvementStock.objects.all()
    serializer_class = serializers.MouvementStockSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF,),
    )]
    # filterset_fields = ["article", "depot", "type_mouvement"]
    filterset_fields = ["article", "depot", "type_mouvement", "document_origine"]
    search_fields = ["numero", "document_origine"]
    # Un mouvement est un fait historique : ni modification ni
    # suppression (sinon StockArticle ne correspondrait plus).
    http_method_names = METHODES_CREATION_LECTURE

    def perform_create(self, serializer):
        # La répercussion sur StockArticle est désormais gérée par le
        # signal post_save de apps/stocks/signals.py, pour qu'elle
        # s'applique aussi aux mouvements créés par les autres modules
        # (production, achats, qualité, distribution, réclamations),
        # pas seulement à ceux créés depuis cet endpoint.
        serializer.save(utilisateur=self.request.user)


class InventaireViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.Inventaire.objects.all()
    serializer_class = serializers.InventaireSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["depot", "statut"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class LigneInventaireViewSet(viewsets.ModelViewSet):
    queryset = models.LigneInventaire.objects.all()
    serializer_class = serializers.LigneInventaireSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["inventaire", "article"]


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))])
def valorisation(request):
    """
    GET /api/stocks/valorisation/?depot=<id>&type_article=MATIERE_PREMIERE
    Valeur du stock au coût moyen pondéré (CMUP), article par article,
    et total. Donnée financière : Comptabilité/DAF, Direction, Admin SI.
    """
    from decimal import Decimal
    stocks = models.StockArticle.objects.select_related("article", "depot", "article__valorisation").filter(quantite_physique__gt=0)
    if request.query_params.get("depot"):
        stocks = stocks.filter(depot_id=request.query_params["depot"])
    if request.query_params.get("type_article"):
        stocks = stocks.filter(article__type_article=request.query_params["type_article"])
    lignes, total = [], Decimal("0")
    for stock in stocks.order_by("article__code", "depot__nom"):
        cmup = getattr(getattr(stock.article, "valorisation", None), "cout_unitaire_moyen", Decimal("0"))
        valeur = (stock.quantite_physique * cmup).quantize(Decimal("0.01"))
        total += valeur
        lignes.append({
            "article": stock.article.code, "designation": stock.article.designation,
            "type_article": stock.article.type_article, "depot": stock.depot.nom,
            "quantite": stock.quantite_physique, "cout_unitaire_moyen": cmup.quantize(Decimal("0.0001")), "valeur": valeur,
        })
    return Response({"valeur_totale": total, "lignes": lignes})
