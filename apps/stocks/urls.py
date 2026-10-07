from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("depots", views.DepotViewSet, basename="depot")
router.register("stock-articles", views.StockArticleViewSet, basename="stockarticle")
router.register("mouvements", views.MouvementStockViewSet, basename="mouvementstock")
router.register("inventaires", views.InventaireViewSet, basename="inventaire")
router.register("lignes-inventaire", views.LigneInventaireViewSet, basename="ligneinventaire")
router.register("transferts", views.TransfertStockViewSet, basename="transfertstock")
router.register("lignes-transfert", views.LigneTransfertViewSet, basename="lignetransfert")
router.register("lots-matieres", views.LotMatiereViewSet, basename="lotmatiere")

from django.urls import path

urlpatterns = [path("valorisation/", views.valorisation, name="valorisation-stock")] + router.urls
