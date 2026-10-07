"""Vues du module coûts - réservé au DAF/Comptabilité et à l'Administrateur SI.
Le Responsable Production ne voit jamais ces données financières
(règle explicite : "ne saisit jamais la valeur financière des matières")."""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import acces
from apps.comptes.models import Profil

# Le DAF saisit et calcule ; la Direction consulte.
PROFILS_COUTS = acces(lecture=(Profil.DIRECTION,), ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI))


class CoutMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.CoutMatiere.objects.all()
    serializer_class = serializers.CoutMatiereSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["article"]


class CoutEnergieViewSet(viewsets.ModelViewSet):
    queryset = models.CoutEnergie.objects.all()
    serializer_class = serializers.CoutEnergieSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["type_energie", "periode"]


class CoutMainOeuvreViewSet(viewsets.ModelViewSet):
    queryset = models.CoutMainOeuvre.objects.all()
    serializer_class = serializers.CoutMainOeuvreSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["ordre_fabrication"]


class AmortissementViewSet(viewsets.ModelViewSet):
    queryset = models.Amortissement.objects.all()
    serializer_class = serializers.AmortissementSerializer
    permission_classes = [PROFILS_COUTS]


class CoutStandardViewSet(viewsets.ModelViewSet):
    queryset = models.CoutStandard.objects.all()
    serializer_class = serializers.CoutStandardSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["article"]


class CoutReelViewSet(viewsets.ModelViewSet):
    queryset = models.CoutReel.objects.all()
    serializer_class = serializers.CoutReelSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["ordre_fabrication"]

    @action(detail=True, methods=["post"])
    def recalculer(self, request, pk=None):
        """
        POST /api/couts/couts-reels/{id}/recalculer/
        Relance le calcul des 4 composantes du coût réel.
        """
        cout_reel = self.get_object()
        cout_reel.calculer()
        return Response(self.get_serializer(cout_reel).data)


# ---------------------------------------------------------------------
# Coûts en cascade
# ---------------------------------------------------------------------
import re

from rest_framework.decorators import api_view, permission_classes as drf_permission_classes

from . import cascade



def _periode(request):
    periode = request.query_params.get("periode") or (request.data.get("periode") if request.method == "POST" else None)
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", periode or ""):
        return None
    return periode


class NatureCoutViewSet(viewsets.ModelViewSet):
    """Paramétrage des éléments de coût (étape, direct/indirect, inducteur, justification) : le DAF les ajuste."""
    queryset = models.NatureCout.objects.select_related("etape")
    serializer_class = serializers.NatureCoutSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["categorie", "categorie_economique", "traitement", "inducteur", "etape", "actif"]
    search_fields = ["libelle", "code"]


class ChargeViewSet(viewsets.ModelViewSet):
    """Charges de la période (factures, salaires, amortissements...), saisies par la DAF."""
    queryset = models.Charge.objects.select_related("nature", "nature__etape", "activite", "ordre_fabrication")
    serializer_class = serializers.ChargeSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["periode", "nature", "activite", "equipement", "ordre_fabrication", "tournee",
                        "statut_donnee", "statut_repartition", "nature__categorie"]
    search_fields = ["numero", "source"]

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)

    @action(detail=True, methods=["get"])
    def cascade(self, request, pk=None):
        """GET .../charges/{id}/cascade/ : la chaîne de calcul complète de la charge (activité -> OF -> produit)."""
        charge = self.get_object()
        lignes = charge.repartitions.select_related("activite", "ordre_fabrication", "article", "etape")
        return Response({
            "charge": serializers.ChargeSerializer(charge).data,
            "repartitions": serializers.RepartitionCoutSerializer(lignes, many=True).data,
        })


class RepartitionCoutViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.RepartitionCout.objects.select_related("charge", "activite", "ordre_fabrication", "article", "etape")
    serializer_class = serializers.RepartitionCoutSerializer
    permission_classes = [acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))]
    filterset_fields = ["charge", "charge__periode", "niveau", "activite", "ordre_fabrication", "article", "etape", "statut"]


@api_view(["POST"])
@drf_permission_classes([acces(ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI))])
def calculer_periode(request):
    """
    POST /api/couts/cascade/calculer/  {"periode": "2026-09"}
    Répartit toutes les charges de la période (charge -> activité -> OF
    -> produit -> pack -> unité), met à jour le coût réel des OF et
    contrôle l'absence de double compte.
    """
    periode = _periode(request)
    if periode is None:
        return Response({"erreur": "Indiquez « periode » au format AAAA-MM."}, status=400)
    return Response(cascade.calculer_periode(periode))


@api_view(["POST"])
@drf_permission_classes([acces(ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI))])
def generer_amortissements(request):
    """POST /api/couts/cascade/amortissements/ {"periode": "2026-09"} : charges d'amortissement depuis les équipements."""
    periode = _periode(request)
    if periode is None:
        return Response({"erreur": "Indiquez « periode » au format AAAA-MM."}, status=400)
    charges = cascade.generer_amortissements(periode, request.user)
    return Response(serializers.ChargeSerializer(charges, many=True).data, status=201)


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))])
def cout_revient(request):
    """GET /api/couts/cascade/cout-revient/?periode=2026-09 : coût par OF, par produit, coût de revient complet."""
    periode = _periode(request)
    if periode is None:
        return Response({"erreur": "Indiquez « periode » au format AAAA-MM."}, status=400)
    return Response(cascade.cout_revient(periode))


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))])
def cout_eau_traitee(request):
    """GET /api/couts/cascade/eau-traitee/?periode=2026-09 : coût de l'eau traitée par activité (par litre et par m³)."""
    periode = _periode(request)
    if periode is None:
        return Response({"erreur": "Indiquez « periode » au format AAAA-MM."}, status=400)
    return Response(cascade.cout_eau_traitee(periode))


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))])
def controle_double_compte(request):
    """GET /api/couts/cascade/controle/?periode=2026-09 : écarts de répartition (liste vide = conforme)."""
    periode = _periode(request)
    if periode is None:
        return Response({"erreur": "Indiquez « periode » au format AAAA-MM."}, status=400)
    anomalies = cascade.controle_non_double_compte(periode)
    return Response({"periode": periode, "conforme": not anomalies, "anomalies": anomalies})
