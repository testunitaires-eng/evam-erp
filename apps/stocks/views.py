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
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
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
    filterset_fields = ["type_lieu", "usine", "activite", "actif"]


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



class TransfertStockViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    """
    Bons de transfert (stock usine -> dépôt extérieur...) : le Magasinier
    prépare et expédie ; le dépôt confirme la réception.
    """
    queryset = models.TransfertStock.objects.select_related("depot_source", "depot_destination").prefetch_related("lignes")
    serializer_class = serializers.TransfertStockSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMMERCIAL, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["statut", "depot_source", "depot_destination"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    def _action(self, request, methode, *args):
        transfert = self.get_object()
        try:
            getattr(transfert, methode)(*args)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(transfert).data)

    @action(detail=True, methods=["post"])
    def expedier(self, request, pk=None):
        """POST .../transferts/{id}/expedier/ : sortie du lieu source (tout ou rien)."""
        return self._action(request, "expedier", request.user)

    @action(detail=True, methods=["post"])
    def receptionner(self, request, pk=None):
        """POST .../transferts/{id}/receptionner/ : entrée au lieu de destination."""
        return self._action(request, "receptionner", request.user)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        return self._action(request, "annuler")

    @action(detail=True, methods=["get"])
    def bon(self, request, pk=None):
        """GET .../transferts/{id}/bon/ : données du bon de transfert à imprimer."""
        transfert = self.get_object()
        return Response({
            "numero": transfert.numero, "statut": transfert.get_statut_display(),
            "de": f"{transfert.depot_source.code} - {transfert.depot_source.nom}",
            "vers": f"{transfert.depot_destination.code} - {transfert.depot_destination.nom}",
            "date_expedition": transfert.date_expedition, "date_reception": transfert.date_reception,
            "expedie_par": transfert.expedie_par.username if transfert.expedie_par_id else None,
            "recu_par": transfert.recu_par.username if transfert.recu_par_id else None,
            "lignes": [
                {"article": l.article.code, "designation": l.article.designation, "quantite": l.quantite,
                 "unite": l.article.unite_mesure, "lot": l.lot.numero_lot if l.lot_id else None}
                for l in transfert.lignes.select_related("article", "lot")
            ],
        })

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/stocks/transferts/{id}/pdf/ : document PDF à imprimer (?telecharger=1 pour le télécharger)."""
        from apps.core import documents
        from apps.core.pdf import telecharger
        objet = self.get_object()
        return documents.bon_transfert(objet, request.user).reponse(f"bon-transfert-{objet.numero}", telecharger(request))


class LigneTransfertViewSet(viewsets.ModelViewSet):
    queryset = models.LigneTransfert.objects.select_related("article", "transfert")
    serializer_class = serializers.LigneTransfertSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMMERCIAL,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["transfert", "article"]


class LotMatiereViewSet(viewsets.ModelViewSet):
    """
    Lots matières / emballages (créés à la réception). Le Magasinier
    saisit les lots d'un stock initial ; la Qualité libère ou bloque.
    """
    queryset = models.LotMatiere.objects.select_related("article", "depot", "fournisseur")
    serializer_class = serializers.LotMatiereSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["article", "depot", "statut", "fournisseur", "lot_fournisseur"]
    search_fields = ["numero", "lot_fournisseur"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _changer(self, request, statut):
        if request.user.profil not in (Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Qualité libère ou bloque un lot matière."}, status=403)
        lot = models.LotMatiere.objects.get(pk=self.kwargs["pk"])
        lot.changer_statut(statut)
        return Response(self.get_serializer(lot).data)

    def get_permissions(self):
        if self.action in ("liberer", "bloquer"):
            from rest_framework.permissions import IsAuthenticated
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def liberer(self, request, pk=None):
        """POST .../lots-matieres/{id}/liberer/ (Responsable Qualité)."""
        return self._changer(request, models.StatutLotMatiere.LIBERE)

    @action(detail=True, methods=["post"])
    def bloquer(self, request, pk=None):
        """POST .../lots-matieres/{id}/bloquer/ (Responsable Qualité)."""
        return self._changer(request, models.StatutLotMatiere.BLOQUE)

    @action(detail=True, methods=["get"])
    def tracabilite(self, request, pk=None):
        """GET .../lots-matieres/{id}/tracabilite/ : traçabilité AVAL (OF -> lots de produits finis), ex. pour un rappel."""
        from apps.production.models import ConsommationLotMatiere
        lot = self.get_object()
        consommations = ConsommationLotMatiere.objects.filter(lot=lot).select_related("sortie__ordre_fabrication__article")
        ofs = {}
        for consommation in consommations:
            of = consommation.sortie.ordre_fabrication
            ligne = ofs.setdefault(of.pk, {
                "of": of.numero, "article": of.article.code, "statut": of.get_statut_display(), "quantite_consommee": 0,
                "lots_produits_finis": [
                    {"lot": l.numero_lot, "quantite": l.quantite, "statut": l.get_statut_display()} for l in of.lots.all()
                ],
            })
            ligne["quantite_consommee"] += consommation.quantite_nette
        return Response({
            "lot": lot.numero, "article": lot.article.code, "lot_fournisseur": lot.lot_fournisseur,
            "fournisseur": str(lot.fournisseur) if lot.fournisseur_id else None,
            "date_reception": lot.date_reception, "date_peremption": lot.date_peremption,
            "quantite_initiale": lot.quantite_initiale, "quantite_restante": lot.quantite_restante,
            "statut": lot.get_statut_display(), "ordres_fabrication": list(ofs.values()),
            "controles": [
                {"numero": r.numero, "controle": r.point.designation, "statut": r.get_statut_display(), "valeur": r.valeur}
                for r in lot.resultats_controles.select_related("point")
            ],
        })
