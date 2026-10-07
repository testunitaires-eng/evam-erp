from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("activites", views.ActiviteViewSet, basename="activite")
router.register("usines", views.UsineViewSet, basename="usine")
router.register("etapes", views.EtapeStandardViewSet, basename="etapestandard")
router.register("lignes", views.LigneViewSet, basename="ligne")
router.register("postes", views.PosteViewSet, basename="poste")
router.register("equipements", views.EquipementViewSet, basename="equipement")
router.register("circuits", views.CircuitViewSet, basename="circuit")
router.register("etapes-circuit", views.EtapeCircuitViewSet, basename="etapecircuit")

urlpatterns = router.urls
