from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("couts-matieres", views.CoutMatiereViewSet, basename="coutmatiere")
router.register("couts-energie", views.CoutEnergieViewSet, basename="coutenergie")
router.register("couts-main-oeuvre", views.CoutMainOeuvreViewSet, basename="coutmainoeuvre")
router.register("amortissements", views.AmortissementViewSet, basename="amortissement")
router.register("couts-standards", views.CoutStandardViewSet, basename="coutstandard")
router.register("couts-reels", views.CoutReelViewSet, basename="coutreel")
router.register("natures", views.NatureCoutViewSet, basename="naturecout")
router.register("charges", views.ChargeViewSet, basename="charge")
router.register("repartitions", views.RepartitionCoutViewSet, basename="repartitioncout")

urlpatterns = [
    path("cascade/calculer/", views.calculer_periode, name="couts-calculer-periode"),
    path("cascade/amortissements/", views.generer_amortissements, name="couts-amortissements"),
    path("cascade/cout-revient/", views.cout_revient, name="couts-cout-revient"),
    path("cascade/eau-traitee/", views.cout_eau_traitee, name="couts-eau-traitee"),
    path("cascade/controle/", views.controle_double_compte, name="couts-controle"),
] + router.urls
