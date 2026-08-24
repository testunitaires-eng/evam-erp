from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("fournisseurs", views.FournisseurViewSet, basename="fournisseur")
router.register("contrats-fournisseurs", views.ContratFournisseurViewSet, basename="contratfournisseur")
router.register("catalogue-fournisseurs", views.ArticleFournisseurViewSet, basename="articlefournisseur")
router.register("besoins", views.BesoinApprovisionnementViewSet, basename="besoinapprovisionnement")
router.register("demandes", views.DemandeAchatViewSet, basename="demandeachat")
router.register("commandes", views.CommandeFournisseurViewSet, basename="commandefournisseur")
router.register("lignes-commande", views.LigneCommandeFournisseurViewSet, basename="lignecommandefournisseur")
router.register("receptions", views.ReceptionAchatViewSet, basename="receptionachat")
router.register("lignes-reception", views.LigneReceptionAchatViewSet, basename="lignereceptionachat")
router.register("retours", views.RetourFournisseurViewSet, basename="retourfournisseur")

urlpatterns = router.urls
