from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("codes-fiscaux", views.CodeFiscalViewSet, basename="codefiscal")

urlpatterns = router.urls