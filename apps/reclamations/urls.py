from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("reclamations", views.ReclamationClientViewSet, basename="reclamationclient")
router.register("retours-physiques", views.RetourPhysiqueViewSet, basename="retourphysique")
router.register("controles", views.ControleRetourViewSet, basename="controleretour")
router.register("reconditionnements", views.ReconditionnementViewSet, basename="reconditionnement")
router.register("couts-retours", views.CoutRetourPerteViewSet, basename="coutretourperte")
router.register("solutions", views.SolutionClientViewSet, basename="solutionclient")

urlpatterns = router.urls