# from rest_framework.routers import DefaultRouter
# from . import views

# router = DefaultRouter()
# router.register("codes-fiscaux", views.CodeFiscalViewSet, basename="codefiscal")

# urlpatterns = router.urls


from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("codes-fiscaux", views.CodeFiscalViewSet, basename="codefiscal")
router.register("familles-fiscales", views.FamilleFiscaleViewSet, basename="famillefiscale")

urlpatterns = router.urls