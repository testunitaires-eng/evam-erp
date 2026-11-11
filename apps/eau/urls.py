from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("parametres", views.ParametresEauViewSet, basename="parametreseau")
router.register("caracteristiques-equipements", views.CaracteristiquesEquipementViewSet, basename="caracteristiquesequipement")
router.register("previsions-volumes", views.PrevisionVolumeViewSet, basename="previsionvolume")
router.register("previsions-captage", views.PrevisionCaptageViewSet, basename="previsioncaptage")
router.register("elements-cout", views.ElementCoutViewSet, basename="elementcout")
router.register("versions-elements-cout", views.VersionElementCoutViewSet, basename="versionelementcout")
router.register("couts-standards", views.CoutStandardEauViewSet, basename="coutstandardeau")

urlpatterns = [path("listes/", views.listes, name="eau-listes")] + router.urls
