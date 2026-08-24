from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("utilisateurs", views.UtilisateurViewSet, basename="utilisateur")
router.register("droits", views.MatriceDroitViewSet, basename="matricedroit")
router.register("journal", views.JournalActionViewSet, basename="journalaction")

urlpatterns = router.urls
