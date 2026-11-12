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
router.register("compteurs", views.CompteurViewSet, basename="compteur")
router.register("releves-compteurs", views.ReleveCompteurViewSet, basename="relevecompteur")
router.register("exceptions-heures", views.ExceptionHeuresViewSet, basename="exceptionheures")
router.register("releves-pression", views.RelevePressionViewSet, basename="relevepression")
router.register("pertes", views.PerteEauViewSet, basename="perteeau")
router.register("interventions", views.InterventionViewSet, basename="intervention")
router.register("installations", views.InstallationViewSet, basename="installation")

urlpatterns = [
    path("listes/", views.listes, name="eau-listes"),
    path("traitement/synthese/", views.synthese_traitement, name="eau-synthese-traitement"),
    path("maintenance/echeances/", views.echeances_maintenance, name="eau-echeances-maintenance"),
] + router.urls
