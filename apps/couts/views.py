"""Vues du module coûts - réservé au DAF/Comptabilité et à l'Administrateur SI.
Le Responsable Production ne voit jamais ces données financières
(règle explicite : "ne saisit jamais la valeur financière des matières")."""

from drf_spectacular.utils import extend_schema
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


@extend_schema(deprecated=True, description="Obsolète : remplacé par les charges des coûts en cascade (/api/couts/charges/).")
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


@extend_schema(deprecated=True, description="Obsolète : remplacé par /api/couts/cascade/amortissements/ (depuis les équipements).")
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
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes

from apps.core.serializers import erreur_django_vers_drf

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
    queryset = models.Charge.objects.select_related("nature", "nature__etape", "activite", "usine", "facture", "ordre_fabrication")
    serializer_class = serializers.ChargeSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["periode", "nature", "activite", "usine", "facture", "equipement", "ordre_fabrication", "tournee",
                        "statut_donnee", "statut_repartition", "nature__categorie"]
    search_fields = ["numero", "source"]

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)

    @action(detail=True, methods=["get"])
    def cascade(self, request, pk=None):
        """GET .../charges/{id}/cascade/ : la chaîne de calcul complète de la charge (site -> activité -> OF -> produit)."""
        charge = self.get_object()
        lignes = charge.repartitions.select_related("usine", "activite", "ordre_fabrication", "article", "etape")
        return Response({
            "charge": serializers.ChargeSerializer(charge).data,
            "repartitions": serializers.RepartitionCoutSerializer(lignes, many=True).data,
        })


class RepartitionCoutViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.RepartitionCout.objects.select_related("charge", "usine", "activite", "ordre_fabrication", "article", "etape")
    serializer_class = serializers.RepartitionCoutSerializer
    permission_classes = [acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))]
    filterset_fields = ["charge", "charge__periode", "niveau", "usine", "activite", "ordre_fabrication", "article", "etape", "statut"]


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



class FactureChargeViewSet(viewsets.ModelViewSet):
    """
    Factures à découper (schéma « coût total d'électricité ») : une facture
    SBEE se ventile en forage commun, site Eau, site Jus & Yaourt et
    infrastructures communes. Chaque part devient une charge de la cascade.
    """
    queryset = models.FactureCharge.objects.prefetch_related("parts__nature__etape", "parts__usine", "parts__activite", "parts__facture")
    serializer_class = serializers.FactureChargeSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["periode"]
    search_fields = ["numero", "reference", "fournisseur"]

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)

    @action(detail=True, methods=["post"])
    def ventiler(self, request, pk=None):
        """
        POST .../factures/{id}/ventiler/
        {"parts": [{"nature": 1, "montant": "6000"}, {"nature": 14, "montant": "2500", "usine": 2}, ...]}
        Remplace toutes les parts de la facture ; la somme doit être
        exactement égale au montant de la facture (sinon rien n'est enregistré).
        """
        facture = self.get_object()
        parts = serializers.PartFactureSerializer(data=request.data.get("parts") or [], many=True)
        parts.is_valid(raise_exception=True)
        if not parts.validated_data:
            return Response({"parts": "Indiquez au moins une part."}, status=400)
        total = sum((part["montant"] for part in parts.validated_data), Decimal(0))
        if total != facture.montant_total:
            return Response({"parts": (
                f"La somme des parts ({total}) doit être égale au montant de la facture ({facture.montant_total})."
            )}, status=400)
        try:
            with transaction.atomic():
                facture.parts.all().delete()
                for part in parts.validated_data:
                    models.Charge.objects.create(
                        facture=facture, periode=facture.periode, source=facture.reference, saisi_par=request.user, **part,
                    )
        except DjangoValidationError as erreur:
            raise erreur_django_vers_drf(erreur)
        return Response(self.get_serializer(self.get_queryset().get(pk=facture.pk)).data)

    @action(detail=True, methods=["post"])
    def repartir_par_etape(self, request, pk=None):
        """
        POST .../factures/{id}/repartir_par_etape/
        Une part par étape au prorata des kWh relevés aux compteurs (relevés
        d'électricité). Sans relevé : ventilez la facture vous-même (/ventiler/).
        """
        facture = self.get_object()
        try:
            cascade.ventiler_facture_par_etape(facture, request.user)
        except DjangoValidationError as erreur:
            raise erreur_django_vers_drf(erreur)
        return Response(self.get_serializer(self.get_queryset().get(pk=facture.pk)).data)


class VolumeEauSiteViewSet(viewsets.ModelViewSet):
    """Relevés des compteurs d'eau brute captée, par activité ou par site : clé du forage commun."""
    queryset = models.VolumeEauSite.objects.select_related("usine", "activite")
    serializer_class = serializers.VolumeEauSiteSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["periode", "usine", "activite", "statut_donnee"]

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)


class ValeurCleViewSet(viewsets.ModelViewSet):
    """Valeurs des clés de site (surface, effectif, temps d'utilisation) par usine et par activité."""
    queryset = models.ValeurCle.objects.select_related("usine", "activite")
    serializer_class = serializers.ValeurCleSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["inducteur", "usine", "activite"]

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))])
def cout_par_site(request):
    """GET /api/couts/cascade/par-site/?periode=2026-09 : charges, électricité et rentabilité par site et par activité."""
    periode = _periode(request)
    if periode is None:
        return Response({"erreur": "Indiquez « periode » au format AAAA-MM."}, status=400)
    return Response(cascade.cout_par_site(periode))


class ReleveElectriciteViewSet(viewsets.ModelViewSet):
    """kWh par étape relevés aux compteurs : clé de répartition de la facture d'électricité par étape."""
    queryset = models.ReleveElectricite.objects.select_related("etape", "nature", "usine", "activite")
    serializer_class = serializers.ReleveElectriciteSerializer
    permission_classes = [PROFILS_COUTS]
    filterset_fields = ["periode", "etape", "usine", "activite", "facture", "statut_donnee"]

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)
