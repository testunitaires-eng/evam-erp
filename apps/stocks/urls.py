from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("depots", views.DepotViewSet, basename="depot")
router.register("stock-articles", views.StockArticleViewSet, basename="stockarticle")
router.register("mouvements", views.MouvementStockViewSet, basename="mouvementstock")
router.register("inventaires", views.InventaireViewSet, basename="inventaire")
router.register("lignes-inventaire", views.LigneInventaireViewSet, basename="ligneinventaire")

urlpatterns = router.urls
