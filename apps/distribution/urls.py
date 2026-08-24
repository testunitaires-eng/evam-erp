from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("vehicules", views.VehiculeViewSet, basename="vehicule")
router.register("chauffeurs", views.ChauffeurViewSet, basename="chauffeur")
router.register("depots", views.DepotViewSet, basename="depot-distribution")
router.register("tournees", views.TourneeViewSet, basename="tournee")
router.register("preparations", views.PreparationLivraisonViewSet, basename="preparationlivraison")
router.register("bons-livraison", views.BonLivraisonViewSet, basename="bonlivraison")
router.register("transferts", views.TransfertDepotViewSet, basename="transfertdepot")

urlpatterns = router.urls
