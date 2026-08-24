from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("caisses", views.CaisseViewSet, basename="caisse")
router.register("sessions", views.SessionCaisseViewSet, basename="sessioncaisse")
router.register("encaissements", views.EncaissementViewSet, basename="encaissement")
router.register("ecarts", views.EcartCaisseViewSet, basename="ecartcaisse")

urlpatterns = router.urls
