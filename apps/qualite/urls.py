from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("lots", views.LotViewSet, basename="lot")
router.register("controles", views.ControleQualiteViewSet, basename="controlequalite")

urlpatterns = router.urls
