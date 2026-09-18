
# from rest_framework.routers import DefaultRouter
# from . import views

# router = DefaultRouter()
# router.register("articles", views.ArticleViewSet, basename="article")
# router.register("fiches-techniques", views.FicheTechniqueViewSet, basename="fichetechnique")
# router.register("compositions", views.CompositionFicheTechniqueViewSet, basename="composition")
# router.register("fiches-conditionnement", views.FicheConditionnementViewSet, basename="ficheconditionnement")
# router.register("controles-qualite-requis", views.ControleQualiteRequisViewSet, basename="controlequaliterequis")

# urlpatterns = router.urls

from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("articles", views.ArticleViewSet, basename="article")
router.register("fiches-techniques", views.FicheTechniqueViewSet, basename="fichetechnique")
router.register("compositions", views.CompositionFicheTechniqueViewSet, basename="composition")
router.register("fiches-conditionnement", views.FicheConditionnementViewSet, basename="ficheconditionnement")
router.register("controles-qualite-requis", views.ControleQualiteRequisViewSet, basename="controlequaliterequis")
router.register("familles", views.FamilleArticleViewSet, basename="famillearticle")
router.register("formats", views.FormatArticleViewSet, basename="formatarticle")
router.register("parfums", views.ParfumViewSet, basename="parfum")
router.register("unites-vente", views.UniteVenteArticleViewSet, basename="unitventearticle")

urlpatterns = router.urls