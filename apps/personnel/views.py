"""
Vues du module personnel.

Le registre des ouvriers et leurs affectations sont tenus par le
Responsable Production (et l'Administrateur SI). La Direction, la
Comptabilité/DAF et les agents de production (chefs d'équipe) les
consultent. Les ouvriers eux-mêmes n'ont jamais de compte.
"""

from datetime import date as Date

from django.db.models import Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.comptes.models import Profil
from apps.comptes.permissions import acces
from . import models, serializers

PERMISSIONS_PERSONNEL = acces(
    lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF, Profil.AGENT_PRODUCTION),
    ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI),
)


def date_du_parametre(request, nom, defaut=None):
    valeur = request.query_params.get(nom)
    if not valeur:
        return defaut
    try:
        return Date.fromisoformat(valeur)
    except ValueError:
        raise ValidationError({nom: "Date attendue au format AAAA-MM-JJ."})


class OuvrierViewSet(viewsets.ModelViewSet):
    """
    Registre des ouvriers. Filtres : ?type_contrat=, ?actif=, ?usine=,
    ?competences=<étape> ; recherche : ?search= (matricule, nom, prénom, téléphone).
    """
    queryset = models.Ouvrier.objects.select_related("usine").prefetch_related("competences")
    serializer_class = serializers.OuvrierSerializer
    permission_classes = [PERMISSIONS_PERSONNEL]
    filterset_fields = ["type_contrat", "actif", "usine", "competences"]
    search_fields = ["matricule", "nom", "prenom", "telephone"]

    @action(detail=False, methods=["get"])
    def disponibles(self, request):
        """
        GET /api/personnel/ouvriers/disponibles/?etape=<id>&date=AAAA-MM-JJ[&usine=<id>]
        Ouvriers actifs, sous contrat à cette date (aujourd'hui par défaut),
        compétents pour l'étape et sans affectation de poste ce jour-là.
        """
        jour = date_du_parametre(request, "date", timezone.localdate())
        etape = request.query_params.get("etape")
        if not etape:
            raise ValidationError({"etape": "Paramètre obligatoire."})
        ouvriers = self.get_queryset().filter(
            actif=True, competences=etape, date_entree__lte=jour,
        ).filter(Q(date_fin_contrat__isnull=True) | Q(date_fin_contrat__gte=jour))
        if request.query_params.get("usine"):
            ouvriers = ouvriers.filter(usine=request.query_params["usine"])
        occupes = models.Affectation.objects.filter(
            ordre_fabrication__isnull=True, date_debut__lte=jour,
        ).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour)).values("ouvrier_id")
        ouvriers = ouvriers.exclude(pk__in=occupes).distinct()
        return Response(self.get_serializer(ouvriers, many=True).data)


class AffectationViewSet(viewsets.ModelViewSet):
    """
    Affectations des ouvriers. Filtres : ?ouvrier=, ?etape=, ?poste=,
    ?ordre_fabrication= (équipe d'un OF), ?active_le=AAAA-MM-JJ.
    """
    queryset = models.Affectation.objects.select_related("ouvrier", "etape", "poste", "ordre_fabrication")
    serializer_class = serializers.AffectationSerializer
    permission_classes = [PERMISSIONS_PERSONNEL]
    filterset_fields = ["ouvrier", "etape", "poste", "ordre_fabrication"]

    def get_queryset(self):
        queryset = super().get_queryset()
        jour = date_du_parametre(self.request, "active_le")
        if jour:
            queryset = queryset.filter(date_debut__lte=jour).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
        return queryset

    def perform_create(self, serializer):
        serializer.save(affecte_par=self.request.user)
