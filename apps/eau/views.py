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
from . import calculs, maintenance, models, reel, serializers, traitement

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


# =====================================================================
# Phase 3 - saisies du traitement de l'eau (techniciens, sans coûts)
# =====================================================================

LECTEURS_TRAITEMENT = CONSULTATION + (Profil.CONTROLE_GESTION, Profil.TECHNICIEN_EAU, Profil.RESPONSABLE_PRODUCTION)
SAISIE_TECHNICIENS = acces(lecture=LECTEURS_TRAITEMENT, ecriture=(Profil.TECHNICIEN_EAU,))


class SaisieViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)


class CompteurViewSet(viewsets.ModelViewSet):
    """Compteur du forage et débitmètres (renseignés par les techniciens)."""
    queryset = models.Compteur.objects.select_related("usine", "site_desservi")
    serializer_class = serializers.CompteurSerializer
    permission_classes = [acces(lecture=LECTEURS_TRAITEMENT, ecriture=(Profil.TECHNICIEN_EAU, Profil.CONTROLE_GESTION))]
    filterset_fields = ["usine", "type_compteur", "site_desservi", "actif"]


class ReleveCompteurViewSet(SaisieViewSet):
    queryset = models.ReleveCompteur.objects.select_related("compteur", "saisi_par")
    serializer_class = serializers.ReleveCompteurSerializer
    permission_classes = [SAISIE_TECHNICIENS]
    filterset_fields = {"compteur": ["exact"], "compteur__usine": ["exact"], "date": ["exact", "gte", "lte"]}


class ExceptionHeuresViewSet(SaisieViewSet):
    """Exceptions d'heures machine : techniciens, et la Production pour ses machines."""
    queryset = models.ExceptionHeures.objects.select_related("equipement", "ligne", "saisi_par")
    serializer_class = serializers.ExceptionHeuresSerializer
    permission_classes = [acces(lecture=LECTEURS_TRAITEMENT, ecriture=(Profil.TECHNICIEN_EAU, Profil.RESPONSABLE_PRODUCTION))]
    filterset_fields = {"equipement": ["exact"], "ligne": ["exact"], "motif": ["exact"], "date": ["exact", "gte", "lte"]}


class RelevePressionViewSet(SaisieViewSet):
    queryset = models.RelevePression.objects.select_related("equipement", "saisi_par")
    serializer_class = serializers.RelevePressionSerializer
    permission_classes = [SAISIE_TECHNICIENS]
    filterset_fields = {"equipement": ["exact"], "date": ["exact", "gte", "lte"]}


class PerteEauViewSet(SaisieViewSet):
    """Pertes d'eau : techniciens et production."""
    queryset = models.PerteEau.objects.select_related("usine", "article", "saisi_par")
    serializer_class = serializers.PerteEauSerializer
    permission_classes = [acces(
        lecture=LECTEURS_TRAITEMENT,
        ecriture=(Profil.TECHNICIEN_EAU, Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION),
    )]
    filterset_fields = {"usine": ["exact"], "type_perte": ["exact"], "cause": ["exact"], "date": ["exact", "gte", "lte"]}


@api_view(["GET"])
@permission_classes([acces(lecture=LECTEURS_TRAITEMENT)])
def synthese_traitement(request):
    """GET /api/eau/traitement/synthese/?usine=<id>&mois=AAAA-MM : volumes, partage du forage, heures machine, pertes du mois."""
    from apps.industriel.models import Usine
    mois = _mois_demande(request)
    valeur = request.query_params.get("usine", "")
    usine = Usine.objects.filter(pk=valeur).first() if valeur.isdigit() else None
    if usine is None or mois is None:
        return Response({"erreur": "Paramètres attendus : usine=<id> et mois=AAAA-MM."}, status=400)
    return Response(traitement.sans_valeurs_exactes(traitement.synthese_mois(usine, mois)))


# =====================================================================
# Phase 4 - maintenance
# =====================================================================

class InterventionViewSet(SaisieViewSet):
    """Interventions de maintenance (techniciens, sans montant)."""
    queryset = models.Intervention.objects.select_related("equipement", "operation", "element_remplace", "saisi_par")
    serializer_class = serializers.InterventionSerializer
    permission_classes = [SAISIE_TECHNICIENS]
    filterset_fields = {
        "equipement": ["exact"], "equipement__usine": ["exact"], "type_intervention": ["exact"],
        "operation": ["exact"], "element_remplace": ["exact"], "date": ["exact", "gte", "lte"],
    }


class InstallationViewSet(SaisieViewSet):
    """Pièces étalées en place, lot par lot, avec leur prix (contrôle de gestion)."""
    queryset = models.Installation.objects.select_related("element", "remplace", "intervention", "saisi_par")
    serializer_class = serializers.InstallationSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["element", "element__usine", "mois_installation", "remplace", "intervention"]


@api_view(["GET"])
@permission_classes([acces(lecture=LECTEURS_TRAITEMENT)])
def echeances_maintenance(request):
    """GET /api/eau/maintenance/echeances/?usine=<id> : opérations préventives à faire et fins de vie (sans coûts)."""
    from apps.industriel.models import Usine
    valeur = request.query_params.get("usine", "")
    usine = Usine.objects.filter(pk=valeur).first() if valeur.isdigit() else None
    if usine is None:
        return Response({"erreur": "Paramètre attendu : usine=<id>."}, status=400)
    return Response(maintenance.echeances(usine))


# =====================================================================
# Phase 5 - coût réel et clôture
# =====================================================================

def _usine_et_mois(request, source):
    from apps.industriel.models import Usine
    valeur, mois = str(source.get("usine") or ""), source.get("mois") or ""
    usine = Usine.objects.filter(pk=valeur).first() if valeur.isdigit() else None
    if usine is None or not models.FORMAT_MOIS.fullmatch(mois):
        return None, None
    return usine, mois


class ValidationSansImputationViewSet(viewsets.ModelViewSet):
    """Charges attendues absentes validées « sans imputation » (comptabilité ou contrôle de gestion), avec un motif."""
    queryset = models.ValidationSansImputation.objects.select_related("element", "valide_par")
    serializer_class = serializers.ValidationSansImputationSerializer
    permission_classes = [acces(lecture=CONSULTATION, ecriture=(Profil.COMPTABILITE_DAF, Profil.CONTROLE_GESTION))]
    filterset_fields = ["element", "element__usine", "mois"]

    def perform_create(self, serializer):
        serializer.save(valide_par=self.request.user)


class ClotureMoisEauViewSet(viewsets.ReadOnlyModelViewSet):
    """Clôtures des mois (coût réel conservé). POST .../clotures/cloturer/ {"usine", "mois"} : contrôle de gestion."""
    queryset = models.ClotureMoisEau.objects.select_related("usine", "cloture_par")
    serializer_class = serializers.ClotureMoisEauSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["usine", "mois"]

    @action(detail=False, methods=["post"])
    def cloturer(self, request):
        usine, mois = _usine_et_mois(request, request.data)
        if usine is None:
            return Response({"erreur": "Paramètres attendus : usine=<id> et mois=AAAA-MM."}, status=400)
        try:
            cloture = reel.cloturer(usine, mois, request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(cloture).data, status=201)


class ValorisationEauOFViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = models.ValorisationEauOF.objects.select_related("cloture", "ordre_fabrication")
    serializer_class = serializers.ValorisationEauOFSerializer
    permission_classes = [PARAMETRES]
    filterset_fields = ["cloture", "cloture__usine", "cloture__mois", "ordre_fabrication"]


@api_view(["GET"])
@permission_classes([PARAMETRES])
def cout_reel(request):
    """GET /api/eau/reel/calcul/?usine=<id>&mois=AAAA-MM : coût réel du mois (calculé à la volée ; mois clôturé : le résultat conservé)."""
    usine, mois = _usine_et_mois(request, request.query_params)
    if usine is None:
        return Response({"erreur": "Paramètres attendus : usine=<id> et mois=AAAA-MM."}, status=400)
    cloture = models.ClotureMoisEau.objects.filter(usine=usine, mois=mois).first()
    if cloture is not None:
        return Response({**cloture.resultat, "cloture": serializers.ClotureMoisEauSerializer(cloture).data["date_cloture"]})
    return Response({**reel.sans_valeurs_exactes(reel.calcul_reel(usine, mois)), "cloture": None})


@api_view(["GET"])
@permission_classes([PARAMETRES])
def charges_attendues(request):
    """GET /api/eau/reel/charges-attendues/?usine=<id>&mois=AAAA-MM : imputées, validées sans imputation, manquantes."""
    usine, mois = _usine_et_mois(request, request.query_params)
    if usine is None:
        return Response({"erreur": "Paramètres attendus : usine=<id> et mois=AAAA-MM."}, status=400)
    return Response({
        "usine": usine.code, "mois": mois, "date_limite": str(reel.date_limite_cloture(usine, mois)),
        "cloture": models.ClotureMoisEau.objects.filter(usine=usine, mois=mois).exists(),
        "charges": reel.charges_attendues(usine, mois),
    })
