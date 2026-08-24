from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("clients", views.ClientViewSet, basename="client")
router.register("prospects", views.ProspectViewSet, basename="prospect")
router.register("contrats", views.ContratClientViewSet, basename="contratclient")
router.register("tarifs", views.TarifViewSet, basename="tarif")
router.register("commandes", views.CommandeViewSet, basename="commande")
router.register("lignes-commande", views.LigneCommandeViewSet, basename="lignecommande")
router.register("factures", views.FactureViewSet, basename="facture")

urlpatterns = router.urls
