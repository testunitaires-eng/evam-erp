from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("parametres", views.ParametresEauViewSet, basename="parametreseau")
router.register("caracteristiques-equipements", views.CaracteristiquesEquipementViewSet, basename="caracteristiquesequipement")

urlpatterns = [path("listes/", views.listes, name="eau-listes")] + router.urls
