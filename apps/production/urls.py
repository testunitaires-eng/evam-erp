# from rest_framework.routers import DefaultRouter
# from . import views

# router = DefaultRouter()
# router.register("plans", views.PlanProductionViewSet, basename="planproduction")
# router.register("ordres-fabrication", views.OrdreFabricationViewSet, basename="ordrefabrication")
# router.register("besoins-matieres", views.BesoinMatierePrevuViewSet, basename="besoinmatiereprevu")
# router.register("sorties-matieres", views.SortieMatiereViewSet, basename="sortiematiere")
# router.register("retours-matieres", views.RetourMatiereViewSet, basename="retourmatiere")
# router.register("etapes", views.EtapeProductionViewSet, basename="etapeproduction")
# router.register("pertes", views.PerteProductionViewSet, basename="perteproduction")

# urlpatterns = router.urls


from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("plans", views.PlanProductionViewSet, basename="planproduction")
router.register("ordres-fabrication", views.OrdreFabricationViewSet, basename="ordrefabrication")
router.register("besoins-matieres", views.BesoinMatierePrevuViewSet, basename="besoinmatiereprevu")
router.register("demandes-matieres", views.DemandeMatiereViewSet, basename="demandematiere")
router.register("demandes-complementaires", views.DemandeComplementaireViewSet, basename="demandecomplementaire")
router.register("sorties-matieres", views.SortieMatiereViewSet, basename="sortiematiere")
router.register("retours-matieres", views.RetourMatiereViewSet, basename="retourmatiere")
router.register("suivis-production", views.SuiviProductionViewSet, basename="suiviproduction")
router.register("suivis-eau", views.SuiviEauViewSet, basename="suivieau")
router.register("etapes", views.EtapeProductionViewSet, basename="etapeproduction")
router.register("pertes", views.PerteProductionViewSet, basename="perteproduction")

urlpatterns = [
    path("tableau-de-bord/", views.tableau_de_bord, name="tableau-de-bord-production"),
] + router.urls