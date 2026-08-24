from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("couts-matieres", views.CoutMatiereViewSet, basename="coutmatiere")
router.register("couts-energie", views.CoutEnergieViewSet, basename="coutenergie")
router.register("couts-main-oeuvre", views.CoutMainOeuvreViewSet, basename="coutmainoeuvre")
router.register("amortissements", views.AmortissementViewSet, basename="amortissement")
router.register("couts-standards", views.CoutStandardViewSet, basename="coutstandard")
router.register("couts-reels", views.CoutReelViewSet, basename="coutreel")

urlpatterns = router.urls
