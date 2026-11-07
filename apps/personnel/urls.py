from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("ouvriers", views.OuvrierViewSet, basename="ouvrier")
router.register("affectations", views.AffectationViewSet, basename="affectation")
router.register("remunerations", views.ConditionRemunerationViewSet, basename="conditionremuneration")
router.register("pointages", views.PointageViewSet, basename="pointage")

urlpatterns = router.urls
