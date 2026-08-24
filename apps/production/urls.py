from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("plans", views.PlanProductionViewSet, basename="planproduction")
router.register("ordres-fabrication", views.OrdreFabricationViewSet, basename="ordrefabrication")
router.register("besoins-matieres", views.BesoinMatierePrevuViewSet, basename="besoinmatiereprevu")
router.register("sorties-matieres", views.SortieMatiereViewSet, basename="sortiematiere")
router.register("retours-matieres", views.RetourMatiereViewSet, basename="retourmatiere")
router.register("etapes", views.EtapeProductionViewSet, basename="etapeproduction")
router.register("pertes", views.PerteProductionViewSet, basename="perteproduction")

urlpatterns = router.urls
