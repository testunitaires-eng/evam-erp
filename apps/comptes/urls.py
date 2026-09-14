from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("utilisateurs", views.UtilisateurViewSet, basename="utilisateur")
router.register("droits", views.MatriceDroitViewSet, basename="matricedroit")
router.register("journal", views.JournalActionViewSet, basename="journalaction")

urlpatterns = [
    # Route dédiée "qui suis-je" : placée avant le router pour que
    # /moi/ ne soit jamais interprété comme un {id} par le
    # UtilisateurViewSet (qui exige le profil ADMIN_SI).
    path("moi/", views.moi, name="moi"),
] + router.urls

