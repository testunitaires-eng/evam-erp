"""
Vues du module « coût de l'eau » (onglet « Rôles et droits » du classeur) :
- le contrôle de gestion est le seul à créer et modifier les paramètres ;
- les techniciens consultent les données techniques (kW, heures), jamais
  les coûts ni les seuils financiers ;
- Direction, Comptabilité / DAF et Administrateur SI consultent.
"""

from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from apps.comptes.models import Profil
from apps.comptes.permissions import acces
from apps.core.views import HistoriqueMixin
from . import calculs, models, serializers

CONSULTATION = (Profil.DIRECTION, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)
PARAMETRES = acces(lecture=CONSULTATION, ecriture=(Profil.CONTROLE_GESTION,))
TECHNIQUE = acces(
    lecture=CONSULTATION + (Profil.TECHNICIEN_EAU, Profil.RESPONSABLE_PRODUCTION),
    ecriture=(Profil.CONTROLE_GESTION,),
)


def _mois_demande(request):
    mois = request.query_params.get("mois") or models.mois_courant()
    if not models.FORMAT_MOIS.fullmatch(mois):
        return None
    return mois


class VersionneeViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)


class ParametresEauViewSet(VersionneeViewSet):
    queryset = models.ParametresEau.objects.select_related("usine", "saisi_par")
    serializer_class = serializers.ParametresEauSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["usine", "mois_application"]

    @action(detail=False, methods=["get"])
    def en_vigueur(self, request):
        """GET .../parametres/en_vigueur/?usine=<id>&mois=AAAA-MM : version qui s'applique ce mois (mois courant par défaut)."""
        mois = _mois_demande(request)
        if mois is None:
            return Response({"erreur": "Le mois doit être au format AAAA-MM."}, status=400)
        version = models.ParametresEau.en_vigueur(mois, usine_id=request.query_params.get("usine"))
        return Response(self.get_serializer(version).data if version else None)


class CaracteristiquesEquipementViewSet(VersionneeViewSet):
    queryset = models.CaracteristiquesEquipement.objects.select_related(
        "equipement__poste__etape__sous_etape_de", "saisi_par",
    )
    serializer_class = serializers.CaracteristiquesEquipementSerializer
    permission_classes = [TECHNIQUE]
    filterset_fields = ["equipement", "equipement__usine", "mois_application"]

    @action(detail=False, methods=["get"])
    def en_vigueur(self, request):
        """
        GET .../caracteristiques-equipements/en_vigueur/?mois=AAAA-MM&usine=<id> :
        pour chaque équipement, la version qui s'applique ce mois.
        """
        mois = _mois_demande(request)
        if mois is None:
            return Response({"erreur": "Le mois doit être au format AAAA-MM."}, status=400)
        versions = self.get_queryset().filter(mois_application__lte=mois)
        if request.query_params.get("usine"):
            versions = versions.filter(equipement__usine_id=request.query_params["usine"])
        retenues = {}
        for version in versions.order_by("equipement_id", "-mois_application"):
            retenues.setdefault(version.equipement_id, version)
        return Response(self.get_serializer(list(retenues.values()), many=True).data)


def _liste(choix):
    return [{"valeur": valeur, "libelle": libelle} for valeur, libelle in choix.choices]


@api_view(["GET"])
@permission_classes([TECHNIQUE])
def listes(request):
    """GET /api/eau/listes/ : blocs, familles (avec leur formule), catégories, périodes (avec leur coefficient)."""
    return Response({
        "blocs": _liste(models.Bloc),
        "familles": [
            {"valeur": famille.value, "libelle": famille.label, "definition": definition,
             "formule_previsionnel": previsionnel, "en_reel": reel}
            for famille, (definition, previsionnel, reel) in models.FORMULES_FAMILLES.items()
        ],
        "categories": _liste(models.Categorie),
        "periodes": [
            {"valeur": periode.value, "libelle": periode.label, "coefficient": f"{numerateur}/{denominateur}",
             "coefficient_decimal": round(models.coefficient_mensuel(periode), 6)}
            for periode, (numerateur, denominateur) in models.COEFFICIENTS_PERIODES.items()
        ],
    })


# =====================================================================
# Phase 2 - prévisionnel et coût standard
# =====================================================================

class PrevisionVolumeViewSet(VersionneeViewSet):
    """Bouteilles prévues par format (saisies par la Production ou le contrôle de gestion)."""
    queryset = models.PrevisionVolume.objects.select_related("article", "usine", "saisi_par")
    serializer_class = serializers.PrevisionVolumeSerializer
    permission_classes = [acces(lecture=CONSULTATION, ecriture=(Profil.CONTROLE_GESTION, Profil.RESPONSABLE_PRODUCTION))]
    filterset_fields = ["usine", "article", "mois_application"]


class PrevisionCaptageViewSet(VersionneeViewSet):
    queryset = models.PrevisionCaptage.objects.select_related("usine", "saisi_par")
    serializer_class = serializers.PrevisionCaptageSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["usine", "mois_application"]


class ElementCoutViewSet(viewsets.ModelViewSet):
    queryset = models.ElementCout.objects.select_related("etape__sous_etape_de", "equipement", "usine")
    serializer_class = serializers.ElementCoutSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["usine", "etape", "equipement", "famille", "categorie"]
    search_fields = ["libelle"]


class VersionElementCoutViewSet(VersionneeViewSet):
    queryset = models.VersionElementCout.objects.select_related("element", "saisi_par")
    serializer_class = serializers.VersionElementCoutSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["element", "element__usine", "mois_application"]


class CoutStandardEauViewSet(HistoriqueMixin, viewsets.ReadOnlyModelViewSet):
    """
    Versions du coût standard de l'eau. Le logiciel calcule et propose,
    le contrôle de gestion valide ou rejette ; rien ne change seul.
    """
    queryset = models.CoutStandardEau.objects.select_related("usine", "propose_par", "valide_par")
    serializer_class = serializers.CoutStandardEauSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["usine", "statut", "origine", "mois_application"]

    def _usine(self, valeur):
        from apps.industriel.models import Usine
        return Usine.objects.filter(pk=valeur).first() if str(valeur or "").isdigit() else None

    @action(detail=False, methods=["get"])
    def calcul(self, request):
        """GET .../couts-standards/calcul/?usine=<id>&mois=AAAA-MM : le calcul prévisionnel détaillé (rien n'est enregistré)."""
        usine, mois = self._usine(request.query_params.get("usine")), _mois_demande(request)
        if usine is None or mois is None:
            return Response({"erreur": "Paramètres attendus : usine=<id> et mois=AAAA-MM."}, status=400)
        return Response(calculs.sans_valeurs_exactes(calculs.calcul_previsionnel(usine, mois)))

    @action(detail=False, methods=["post"])
    def proposer(self, request):
        """POST .../couts-standards/proposer/ {"usine", "mois_application"} : enregistre le prévisionnel comme standard proposé."""
        usine, mois = self._usine(request.data.get("usine")), request.data.get("mois_application") or ""
        if usine is None or not models.FORMAT_MOIS.fullmatch(mois):
            return Response({"erreur": "Paramètres attendus : usine=<id> et mois_application=AAAA-MM."}, status=400)
        try:
            standard = calculs.proposer_standard(usine, mois, request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(standard).data, status=201)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        standard = self.get_object()
        try:
            standard.valider(request.user, request.data.get("motif", ""))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(standard).data)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        standard = self.get_object()
        try:
            standard.rejeter(request.user, request.data.get("motif", ""))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(standard).data)

    @action(detail=False, methods=["get"])
    def en_vigueur(self, request):
        """GET .../couts-standards/en_vigueur/?usine=<id>&mois=AAAA-MM : le standard validé qui s'applique ce mois."""
        mois = _mois_demande(request)
        if mois is None:
            return Response({"erreur": "Le mois doit être au format AAAA-MM."}, status=400)
        standard = models.CoutStandardEau.en_vigueur(mois, usine_id=request.query_params.get("usine"))
        return Response(self.get_serializer(standard).data if standard else None)
