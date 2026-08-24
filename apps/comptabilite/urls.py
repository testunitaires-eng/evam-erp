from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("anomalies", views.AnomalieDetecteeViewSet, basename="anomaliedetectee")
router.register("exports", views.ExportComptableViewSet, basename="exportcomptable")
router.register("clotures", views.ClotureViewSet, basename="cloture")

urlpatterns = router.urls
