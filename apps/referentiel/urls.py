# from rest_framework.routers import DefaultRouter
# from . import views

# router = DefaultRouter()
# router.register("articles", views.ArticleViewSet, basename="article")
# router.register("fiches-techniques", views.FicheTechniqueViewSet, basename="fichetechnique")
# router.register("compositions", views.CompositionFicheTechniqueViewSet, basename="composition")
# router.register("fiches-conditionnement", views.FicheConditionnementViewSet, basename="ficheconditionnement")

# urlpatterns = router.urls

from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("articles", views.ArticleViewSet, basename="article")
router.register("fiches-techniques", views.FicheTechniqueViewSet, basename="fichetechnique")
router.register("compositions", views.CompositionFicheTechniqueViewSet, basename="composition")
router.register("fiches-conditionnement", views.FicheConditionnementViewSet, basename="ficheconditionnement")
router.register("controles-qualite-requis", views.ControleQualiteRequisViewSet, basename="controlequaliterequis")

urlpatterns = router.urls