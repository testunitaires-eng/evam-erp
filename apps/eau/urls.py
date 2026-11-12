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
router.register("validations-sans-imputation", views.ValidationSansImputationViewSet, basename="validationsansimputation")
router.register("clotures", views.ClotureMoisEauViewSet, basename="cloturemoiseau")
router.register("valorisations-of", views.ValorisationEauOFViewSet, basename="valorisationeauof")

urlpatterns = [
    path("listes/", views.listes, name="eau-listes"),
    path("traitement/synthese/", views.synthese_traitement, name="eau-synthese-traitement"),
    path("maintenance/echeances/", views.echeances_maintenance, name="eau-echeances-maintenance"),
    path("reel/calcul/", views.cout_reel, name="eau-cout-reel"),
    path("reel/charges-attendues/", views.charges_attendues, name="eau-charges-attendues"),
    path("reel/evolution/", views.evolution_cout, name="eau-evolution-cout"),
] + router.urls
