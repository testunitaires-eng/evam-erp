from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("anomalies", views.AnomalieDetecteeViewSet, basename="anomaliedetectee")
router.register("exports", views.ExportComptableViewSet, basename="exportcomptable")
router.register("clotures", views.ClotureViewSet, basename="cloture")
router.register("comptes", views.CompteParametreViewSet, basename="compteparametre")
router.register("seuils-controles", views.ParametreControleViewSet, basename="parametrecontrole")
router.register("ecritures", views.EcritureComptableViewSet, basename="ecriturecomptable")
router.register("regles-comptes", views.RegleCompteViewSet, basename="reglecompte")

urlpatterns = router.urls
