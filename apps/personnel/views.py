"""
Vues du module personnel.

Répartition des rôles (les ouvriers eux-mêmes n'ont jamais de compte) :
- RH : fiches des ouvriers, rémunération, pointages (saisie et validation) ;
- Responsable Production : affectations aux postes et aux OF (avec le RH) ;
  il consulte les ouvriers et les pointages, jamais les montants ;
- Direction, Comptabilité/DAF : consultation (la DAF voit la rémunération) ;
- Agent Production (chef d'équipe) : consultation des ouvriers, affectations
  et pointages.
- Paie : le RH prépare les états, la DAF (ou la Direction) les valide ou
  les annule, le caissier les paie en espèces.
L'Administrateur SI a accès à tout.
"""

from datetime import date as Date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.comptes.models import Profil
from apps.comptes.permissions import acces
from . import models, serializers

PERMISSIONS_OUVRIERS = acces(
    lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.DIRECTION, Profil.COMPTABILITE_DAF, Profil.AGENT_PRODUCTION),
    ecriture=(Profil.RH, Profil.ADMIN_SI),
)
PERMISSIONS_AFFECTATIONS = acces(
    lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF, Profil.AGENT_PRODUCTION),
    ecriture=(Profil.RH, Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI),
)
PERMISSIONS_REMUNERATION = acces(
    lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION),
    ecriture=(Profil.RH, Profil.ADMIN_SI),
)
PERMISSIONS_PAIE = acces(
    ecriture=(Profil.RH, Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.CAISSIER, Profil.ADMIN_SI),
)
PROFILS_PREPARATION_PAIE = (Profil.RH, Profil.ADMIN_SI)
PROFILS_VALIDATION_PAIE = (Profil.COMPTABILITE_DAF, Profil.DIRECTION)   # ils autorisent aussi le décaissement
PROFILS_PAIEMENT = (Profil.CAISSIER,)
PERMISSIONS_POINTAGES = acces(
    lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.AGENT_PRODUCTION),
    ecriture=(Profil.RH, Profil.ADMIN_SI),
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
    permission_classes = [PERMISSIONS_OUVRIERS]
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
    permission_classes = [PERMISSIONS_AFFECTATIONS]
    filterset_fields = ["ouvrier", "etape", "poste", "ordre_fabrication"]

    def get_queryset(self):
        queryset = super().get_queryset()
        jour = date_du_parametre(self.request, "active_le")
        if jour:
            queryset = queryset.filter(date_debut__lte=jour).filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
        return queryset

    def perform_create(self, serializer):
        serializer.save(affecte_par=self.request.user)


class ConditionRemunerationViewSet(viewsets.ModelViewSet):
    """Rémunération des ouvriers (historique par date d'effet). Filtres : ?ouvrier=, ?mode=, ?periodicite_paie=."""
    queryset = models.ConditionRemuneration.objects.select_related("ouvrier")
    serializer_class = serializers.ConditionRemunerationSerializer
    permission_classes = [PERMISSIONS_REMUNERATION]
    filterset_fields = ["ouvrier", "mode", "periodicite_paie"]

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)


class PointageViewSet(viewsets.ModelViewSet):
    """
    Pointages journaliers. Filtres : ?ouvrier=, ?date=, ?statut=, ?presence=,
    ?ordre_fabrication=, et période ?du=AAAA-MM-JJ&au=AAAA-MM-JJ.
    """
    queryset = models.Pointage.objects.select_related("ouvrier", "etape", "poste", "ordre_fabrication")
    serializer_class = serializers.PointageSerializer
    permission_classes = [PERMISSIONS_POINTAGES]
    filterset_fields = ["ouvrier", "date", "statut", "presence", "ordre_fabrication"]

    def get_queryset(self):
        queryset = super().get_queryset()
        du, au = date_du_parametre(self.request, "du"), date_du_parametre(self.request, "au")
        if du:
            queryset = queryset.filter(date__gte=du)
        if au:
            queryset = queryset.filter(date__lte=au)
        return queryset

    def perform_create(self, serializer):
        serializer.save(saisi_par=self.request.user)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """POST /api/personnel/pointages/{id}/valider/"""
        pointage = self.get_object()
        try:
            pointage.valider(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(pointage).data)

    @action(detail=False, methods=["post"])
    def valider_periode(self, request):
        """
        POST /api/personnel/pointages/valider_periode/ {"du": "AAAA-MM-JJ", "au": "AAAA-MM-JJ", "ouvrier": <id facultatif>}
        Valide tous les pointages saisis de la période.
        """
        try:
            du, au = Date.fromisoformat(request.data.get("du", "")), Date.fromisoformat(request.data.get("au", ""))
        except ValueError:
            raise ValidationError({"du": "Indiquez la période : du / au au format AAAA-MM-JJ."})
        a_valider = models.Pointage.objects.filter(statut=models.StatutPointage.SAISI, date__gte=du, date__lte=au)
        if request.data.get("ouvrier"):
            a_valider = a_valider.filter(ouvrier_id=request.data["ouvrier"])
        nombre = 0
        with transaction.atomic():
            for pointage in a_valider.select_for_update():
                pointage.valider(request.user)
                nombre += 1
        return Response({"valides": nombre})

    @action(detail=False, methods=["get"])
    def feuille(self, request):
        """
        GET /api/personnel/pointages/feuille/?date=AAAA-MM-JJ[&usine=<id>]
        Feuille de pointage du jour : chaque ouvrier actif sous contrat, son
        affectation du jour (lieu proposé) et son pointage s'il existe déjà.
        """
        jour = date_du_parametre(request, "date", timezone.localdate())
        ouvriers = models.Ouvrier.objects.filter(actif=True, date_entree__lte=jour).filter(
            Q(date_fin_contrat__isnull=True) | Q(date_fin_contrat__gte=jour),
        )
        if request.query_params.get("usine"):
            ouvriers = ouvriers.filter(usine=request.query_params["usine"])
        pointages = {p.ouvrier_id: p for p in self.get_queryset().filter(date=jour, ouvrier__in=ouvriers)}
        lignes = []
        for ouvrier in ouvriers:
            affectations = ouvrier.affectations_du(jour)
            lignes.append({
                "ouvrier": ouvrier.pk, "matricule": ouvrier.matricule, "nom": ouvrier.nom_complet,
                "type_contrat": ouvrier.type_contrat,
                "affectations": serializers.AffectationSerializer(affectations, many=True).data,
                "pointage": self.get_serializer(pointages[ouvrier.pk]).data if ouvrier.pk in pointages else None,
            })
        return Response({"date": jour, "lignes": lignes})

    @action(detail=False, methods=["post"])
    def saisie_jour(self, request):
        """
        POST /api/personnel/pointages/saisie_jour/
        {"date": "AAAA-MM-JJ", "lignes": [{"ouvrier": 1, "presence": "PRESENT", ...}, ...]}
        Pointe plusieurs ouvriers d'un coup (crée ou corrige les pointages
        non validés). Tout ou rien : si une ligne est refusée, rien n'est
        enregistré et chaque erreur est renvoyée avec son ouvrier.
        """
        jour = request.data.get("date")
        lignes = request.data.get("lignes") or []
        if not jour or not isinstance(lignes, list) or not lignes:
            raise ValidationError({"lignes": "Indiquez la date et au moins une ligne de pointage."})
        erreurs, enregistres = {}, []
        with transaction.atomic():
            for ligne in lignes:
                donnees = {**ligne, "date": jour}
                existant = models.Pointage.objects.filter(ouvrier_id=ligne.get("ouvrier"), date=jour).first()
                serializer = self.get_serializer(existant, data=donnees, partial=existant is not None)
                if serializer.is_valid():
                    try:
                        enregistres.append(serializer.save(**({} if existant else {"saisi_par": request.user})))
                    except DjangoValidationError as erreur:   # refus du modèle (ex : pointage déjà validé)
                        erreurs[str(ligne.get("ouvrier"))] = getattr(erreur, "message_dict", None) or erreur.messages
                else:
                    erreurs[str(ligne.get("ouvrier"))] = serializer.errors
            if erreurs:
                transaction.set_rollback(True)
        if erreurs:
            return Response({"erreurs": erreurs}, status=400)
        return Response(self.get_serializer(enregistres, many=True).data, status=201)


def exiger_profil(request, profils, action):
    if not (request.user.is_superuser or request.user.profil in profils):
        raise PermissionDenied(f"Votre profil ne peut pas {action}.")


class EtatPaieViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    États de paie. Filtres : ?ouvrier=, ?statut=, ?periodicite=, ?date_debut=, ?date_fin=.
    Le caissier ne voit que les états à payer ou payés. Supprimer : état préparé seulement (RH).
    """
    queryset = models.EtatPaie.objects.select_related("ouvrier", "decaissement")
    serializer_class = serializers.EtatPaieSerializer
    permission_classes = [PERMISSIONS_PAIE]
    filterset_fields = ["ouvrier", "statut", "periodicite", "date_debut", "date_fin"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.profil == Profil.CAISSIER and not self.request.user.is_superuser:
            queryset = queryset.filter(statut__in=(models.StatutEtatPaie.VALIDE, models.StatutEtatPaie.PAYE))
        return queryset

    def perform_destroy(self, instance):
        exiger_profil(self.request, PROFILS_PREPARATION_PAIE, "supprimer un état de paie")
        instance.delete()

    def _action(self, request, profils, libelle, methode, *args):
        exiger_profil(request, profils, libelle)
        etat = self.get_object()
        try:
            methode(etat, *args)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(etat).data)

    @action(detail=False, methods=["post"])
    def preparer(self, request):
        """
        POST /api/personnel/etats-paie/preparer/ {"periodicite": "MENSUELLE"|"HEBDOMADAIRE", "date": "AAAA-MM-JJ"}
        Prépare les états de la période contenant la date (RH).
        """
        exiger_profil(request, PROFILS_PREPARATION_PAIE, "préparer la paie")
        periodicite = request.data.get("periodicite")
        if periodicite not in models.PeriodicitePaie.values:
            raise ValidationError({"periodicite": "HEBDOMADAIRE ou MENSUELLE."})
        try:
            jour = Date.fromisoformat(request.data.get("date") or str(timezone.localdate()))
        except ValueError:
            raise ValidationError({"date": "Date attendue au format AAAA-MM-JJ."})
        crees, erreurs = models.EtatPaie.preparer(periodicite, jour, request.user)
        return Response({"etats": self.get_serializer(crees, many=True).data, "erreurs": erreurs}, status=201)

    @action(detail=True, methods=["post"])
    def recalculer(self, request, pk=None):
        """POST .../etats-paie/{id}/recalculer/ (RH, état préparé)."""
        return self._action(request, PROFILS_PREPARATION_PAIE, "recalculer la paie", models.EtatPaie.recalculer)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """POST .../etats-paie/{id}/valider/ (DAF ou Direction)."""
        return self._action(request, PROFILS_VALIDATION_PAIE, "valider la paie", models.EtatPaie.valider, request.user)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        """POST .../etats-paie/{id}/annuler/ {"motif": "..."} (DAF ou Direction, état validé non payé)."""
        return self._action(request, PROFILS_VALIDATION_PAIE, "annuler la paie", models.EtatPaie.annuler,
                            request.user, request.data.get("motif", ""))

    @action(detail=True, methods=["post"])
    def payer(self, request, pk=None):
        """POST .../etats-paie/{id}/payer/ (caissier, session de caisse ouverte)."""
        return self._action(request, PROFILS_PAIEMENT, "payer la paie", models.EtatPaie.payer, request.user)

    @action(detail=False, methods=["get"])
    def emargement(self, request):
        """
        GET .../etats-paie/emargement/?date_debut=AAAA-MM-JJ&date_fin=AAAA-MM-JJ[&periodicite=]
        (ou ?ids=1,2,3) : fiche d'émargement PDF des états validés ou payés.
        """
        from apps.core import documents
        from apps.core.pdf import telecharger
        etats = self.get_queryset().filter(statut__in=(models.StatutEtatPaie.VALIDE, models.StatutEtatPaie.PAYE))
        if request.query_params.get("ids"):
            etats = etats.filter(pk__in=[i for i in request.query_params["ids"].split(",") if i.strip().isdigit()])
        else:
            debut, fin = date_du_parametre(request, "date_debut"), date_du_parametre(request, "date_fin")
            if not (debut and fin):
                raise ValidationError({"date_debut": "Indiquez date_debut et date_fin, ou ids."})
            etats = etats.filter(date_debut__gte=debut, date_fin__lte=fin)
            if request.query_params.get("periodicite"):
                etats = etats.filter(periodicite=request.query_params["periodicite"])
        etats = etats.order_by("ouvrier__nom", "ouvrier__prenom")
        if not etats.exists():
            raise ValidationError({"etats": "Aucun état de paie validé ou payé pour cette sélection."})
        return documents.etat_emargement(etats, request.user).reponse("emargement-paie", telecharger(request))

