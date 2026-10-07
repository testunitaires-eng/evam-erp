from django.urls import path
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register("lots", views.LotViewSet, basename="lot")
router.register("controles", views.ControleQualiteViewSet, basename="controlequalite")
router.register("parametres", views.ParametreQualiteViewSet, basename="parametrequalite")
router.register("instruments", views.InstrumentViewSet, basename="instrument")
router.register("bibliotheque-controles", views.ModeleControleViewSet, basename="modelecontrole")
router.register("plan-controle", views.PointControleViewSet, basename="pointcontrole")
router.register("controles-realises", views.ResultatControleViewSet, basename="resultatcontrole")
router.register("non-conformites", views.NonConformiteViewSet, basename="nonconformite")
router.register("pieces-jointes", views.PieceJointeQualiteViewSet, basename="piecejointequalite")

urlpatterns = [path("indicateurs/", views.indicateurs_qualite, name="indicateurs-qualite")] + router.urls
