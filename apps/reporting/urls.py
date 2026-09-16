from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("rapports", views.RapportGenereViewSet, basename="rapportgenere")

urlpatterns = [
    path("tableau-de-bord-direction/", views.tableau_de_bord_direction, name="tableau-de-bord-direction"),
    path("production/", views.bloc_production, name="reporting-production"),
    path("stock/", views.bloc_stock, name="reporting-stock"),
    path("commercial/", views.bloc_commercial, name="reporting-commercial"),
    path("caisse/", views.bloc_caisse, name="reporting-caisse"),
    path("distribution/", views.bloc_distribution, name="reporting-distribution"),
    path("rentabilite/", views.bloc_rentabilite, name="reporting-rentabilite"),
    path("alertes/", views.bloc_alertes, name="reporting-alertes"),
] + router.urls