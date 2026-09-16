# """
# Vues du module production.

# Le Responsable Production crée le plan et lance les OF ; l'Agent
# Production a un accès plus restreint (seulement ses OF affectés,
# saisie de quantités/temps/pertes/incidents).
# """

# from rest_framework import viewsets
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from django.core.exceptions import ValidationError as DjangoValidationError
# from . import models, serializers
# from apps.comptes.permissions import role_required
# from apps.comptes.models import Profil


# class PlanProductionViewSet(viewsets.ModelViewSet):
#     queryset = models.PlanProduction.objects.all()
#     serializer_class = serializers.PlanProductionSerializer
#     permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
#     filterset_fields = ["article", "statut", "priorite"]

#     def perform_create(self, serializer):
#         serializer.save(cree_par=self.request.user)


# class OrdreFabricationViewSet(viewsets.ModelViewSet):
#     queryset = models.OrdreFabrication.objects.all()
#     serializer_class = serializers.OrdreFabricationSerializer
#     permission_classes = [role_required(
#         Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
#     )]
#     filterset_fields = ["article", "statut"]
#     search_fields = ["numero"]

#     def get_queryset(self):
#         """
#         Un Agent Production ne voit que les OF où il est affecté
#         (agents_affectes), conformément au cahier des charges.
#         """
#         queryset = super().get_queryset()
#         utilisateur = self.request.user
#         if utilisateur.is_superuser:
#             return queryset
#         if utilisateur.profil == Profil.AGENT_PRODUCTION:
#             return queryset.filter(agents_affectes=utilisateur)
#         return queryset

#     def perform_create(self, serializer):
#         serializer.save(responsable=self.request.user)

#     @action(detail=True, methods=["post"])
#     def avancer_statut(self, request, pk=None):
#         """
#         POST /api/production/ordres-fabrication/{id}/avancer_statut/
#         Réservé au Responsable Production.
#         """
#         if request.user.profil not in (Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI) and not request.user.is_superuser:
#             return Response(
#                 {"erreur": "Seul le Responsable Production peut faire avancer le statut de l'OF."},
#                 status=403,
#             )
#         of = self.get_object()
#         try:
#             nouveau_statut = of.passer_statut_suivant()
#         except ValueError as erreur:
#             return Response({"erreur": str(erreur)}, status=400)
#         return Response({"statut": nouveau_statut, "of": self.get_serializer(of).data})


# class BesoinMatierePrevuViewSet(viewsets.ReadOnlyModelViewSet):
#     """Lecture seule : calculé automatiquement, jamais saisi à la main."""
#     queryset = models.BesoinMatierePrevu.objects.all()
#     serializer_class = serializers.BesoinMatierePrevuSerializer
#     permission_classes = [role_required(
#         Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,
#     )]
#     filterset_fields = ["ordre_fabrication", "matiere"]


# class SortieMatiereViewSet(viewsets.ModelViewSet):
#     queryset = models.SortieMatiere.objects.all()
#     serializer_class = serializers.SortieMatiereSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
#     filterset_fields = ["ordre_fabrication", "matiere", "type_sortie"]

#     def perform_create(self, serializer):
#         """
#         Le motif obligatoire pour une sortie complémentaire est vérifié
#         par Model.clean() ; on l'appelle explicitement ici car
#         ModelSerializer ne l'invoque pas automatiquement.
#         """
#         instance = serializer.save()
#         try:
#             instance.clean()
#         except DjangoValidationError:
#             instance.delete()
#             raise


# class RetourMatiereViewSet(viewsets.ModelViewSet):
#     queryset = models.RetourMatiere.objects.all()
#     serializer_class = serializers.RetourMatiereSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
#     filterset_fields = ["ordre_fabrication", "matiere"]


# class EtapeProductionViewSet(viewsets.ModelViewSet):
#     queryset = models.EtapeProduction.objects.all()
#     serializer_class = serializers.EtapeProductionSerializer
#     permission_classes = [role_required(
#         Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
#     )]
#     filterset_fields = ["ordre_fabrication", "etape"]

#     def get_queryset(self):
#         """Un Agent Production ne voit que les étapes des OF où il est affecté."""
#         queryset = super().get_queryset()
#         utilisateur = self.request.user
#         if utilisateur.is_superuser:
#             return queryset
#         if utilisateur.profil == Profil.AGENT_PRODUCTION:
#             return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
#         return queryset

#     def perform_create(self, serializer):
#         serializer.save(agent=self.request.user)


# class PerteProductionViewSet(viewsets.ModelViewSet):
#     queryset = models.PerteProduction.objects.all()
#     serializer_class = serializers.PerteProductionSerializer
#     permission_classes = [role_required(
#         Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
#     )]
#     filterset_fields = ["ordre_fabrication", "motif"]

#     def get_queryset(self):
#         """Un Agent Production ne voit que les pertes des OF où il est affecté."""
#         queryset = super().get_queryset()
#         utilisateur = self.request.user
#         if utilisateur.is_superuser:
#             return queryset
#         if utilisateur.profil == Profil.AGENT_PRODUCTION:
#             return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
#         return queryset


"""
Vues du module production (cahier des charges mis à jour, §5).

Contient le tableau de bord production (§5.2), le workflow de l'OF
réaligné sur les nouveaux statuts, et les nouvelles rubriques :
demandes de matières, demandes complémentaires, suivi de production,
suivi spécifique de l'eau.
"""

from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from . import models, serializers
from apps.comptes.permissions import role_required
from apps.comptes.models import Profil


class PlanProductionViewSet(viewsets.ModelViewSet):
    queryset = models.PlanProduction.objects.all()
    serializer_class = serializers.PlanProductionSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
    filterset_fields = ["article", "statut", "priorite"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def convertir_en_of(self, request, pk=None):
        """
        POST /api/production/plans/{id}/convertir_en_of/
        Transforme la prévision en OF réel (§5.3). Déclenche
        automatiquement le calcul des besoins matières.
        """
        plan = self.get_object()
        try:
            of = plan.convertir_en_of(responsable=request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(serializers.OrdreFabricationSerializer(of).data, status=201)


class OrdreFabricationViewSet(viewsets.ModelViewSet):
    queryset = models.OrdreFabrication.objects.all()
    serializer_class = serializers.OrdreFabricationSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
    filterset_fields = ["article", "statut"]
    search_fields = ["numero"]

    def get_queryset(self):
        """Un Agent Production ne voit que les OF où il est affecté."""
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(agents_affectes=utilisateur)
        return queryset

    def perform_create(self, serializer):
        serializer.save(responsable=self.request.user)

    @action(detail=True, methods=["post"])
    def avancer_statut(self, request, pk=None):
        """POST .../avancer_statut/ - réservé au Responsable Production."""
        if request.user.profil not in (Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Production peut faire avancer le statut de l'OF."}, status=403)
        of = self.get_object()
        try:
            nouveau_statut = of.passer_statut_suivant()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response({"statut": nouveau_statut, "of": self.get_serializer(of).data})

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        """
        POST .../annuler/  Corps : {"motif": "..."} (obligatoire).
        Réservé au Responsable Production.
        """
        if request.user.profil not in (Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Production peut annuler un OF."}, status=403)
        of = self.get_object()
        try:
            of.annuler(motif=request.data.get("motif", ""))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(of).data)

    @action(detail=True, methods=["get"])
    def consommation_reelle(self, request, pk=None):
        """
        GET .../consommation_reelle/
        §5.10 : théorique / réelle / écart, matière par matière.
        """
        of = self.get_object()
        return Response(of.calculer_consommation_reelle())

    @action(detail=True, methods=["get"])
    def synthese_cloture(self, request, pk=None):
        """
        GET .../synthese_cloture/
        §5.14 : page de synthèse avant clôture (prévision / réel / écarts).
        Ne calcule pas les coûts (voir apps.couts.CoutReel, séparé).
        """
        of = self.get_object()
        consommation = of.calculer_consommation_reelle()
        try:
            suivi_eau = serializers.SuiviEauSerializer(of.suivi_eau).data
        except models.SuiviEau.DoesNotExist:
            suivi_eau = None
        return Response({
            "numero": of.numero,
            "statut": of.statut,
            "quantite_prevue": of.quantite_a_produire,
            "consommation_matieres": consommation,
            "suivi_eau": suivi_eau,
            "pertes": serializers.PerteProductionSerializer(of.pertes.all(), many=True).data,
        })


class BesoinMatierePrevuViewSet(viewsets.ReadOnlyModelViewSet):
    """Lecture seule : calculé automatiquement à la création de l'OF."""
    queryset = models.BesoinMatierePrevu.objects.all()
    serializer_class = serializers.BesoinMatierePrevuSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication", "matiere"]

    def list(self, request, *args, **kwargs):
        """Ajoute stock_disponible / manquant / situation (§5.5) à chaque ligne, sans les stocker en base."""
        reponse = super().list(request, *args, **kwargs)
        for item, obj in zip(reponse.data.get("results", reponse.data), self.filter_queryset(self.get_queryset())):
            item["stock_disponible"] = obj.stock_disponible()
            item["manquant"] = obj.manquant()
            item["situation"] = obj.situation()
        return reponse


class DemandeMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.DemandeMatiere.objects.all()
    serializer_class = serializers.DemandeMatiereSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication", "matiere", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(demandeur=self.request.user)

    @action(detail=True, methods=["post"])
    def livrer(self, request, pk=None):
        """
        POST .../livrer/  Corps optionnel : {"quantite_livree": ...}
        Réservé au Magasinier. Génère automatiquement la sortie matière.
        """
        if request.user.profil not in (Profil.MAGASINIER, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Magasinier peut livrer une demande de matière."}, status=403)
        demande = self.get_object()
        try:
            demande.livrer_a_production(quantite_livree=request.data.get("quantite_livree"))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(demande).data)


class DemandeComplementaireViewSet(viewsets.ModelViewSet):
    queryset = models.DemandeComplementaire.objects.all()
    serializer_class = serializers.DemandeComplementaireSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication", "matiere", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(demandeur=self.request.user)

    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):
        """POST .../approuver/ - réservé au Magasinier, génère la sortie complémentaire automatiquement."""
        if request.user.profil not in (Profil.MAGASINIER, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Magasinier peut approuver une demande complémentaire."}, status=403)
        demande = self.get_object()
        try:
            demande.approuver_et_livrer(utilisateur=request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        """POST .../rejeter/ - réservé au Magasinier."""
        if request.user.profil not in (Profil.MAGASINIER, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Magasinier peut rejeter une demande complémentaire."}, status=403)
        demande = self.get_object()
        demande.rejeter()
        return Response(self.get_serializer(demande).data)


class SortieMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.SortieMatiere.objects.all()
    serializer_class = serializers.SortieMatiereSerializer
    permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
    filterset_fields = ["ordre_fabrication", "matiere", "type_sortie"]

    def perform_create(self, serializer):
        instance = serializer.save()
        try:
            instance.clean()
        except DjangoValidationError as erreur:
            instance.delete()
            raise DRFValidationError(erreur.messages if hasattr(erreur, "messages") else str(erreur))


class RetourMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.RetourMatiere.objects.all()
    serializer_class = serializers.RetourMatiereSerializer
    permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
    filterset_fields = ["ordre_fabrication", "matiere"]


class SuiviProductionViewSet(viewsets.ModelViewSet):
    queryset = models.SuiviProduction.objects.all()
    serializer_class = serializers.SuiviProductionSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication", "date"]

    def get_queryset(self):
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
        return queryset


class SuiviEauViewSet(viewsets.ModelViewSet):
    queryset = models.SuiviEau.objects.all()
    serializer_class = serializers.SuiviEauSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication"]


class EtapeProductionViewSet(viewsets.ModelViewSet):
    queryset = models.EtapeProduction.objects.all()
    serializer_class = serializers.EtapeProductionSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication", "etape"]

    def get_queryset(self):
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
        return queryset

    def perform_create(self, serializer):
        serializer.save(agent=self.request.user)


class PerteProductionViewSet(viewsets.ModelViewSet):
    queryset = models.PerteProduction.objects.all()
    serializer_class = serializers.PerteProductionSerializer
    permission_classes = [role_required(
        Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
    )]
    filterset_fields = ["ordre_fabrication", "motif"]

    def get_queryset(self):
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.is_superuser:
            return queryset
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
        return queryset


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def tableau_de_bord(request):
    """
    GET /api/production/tableau-de-bord/

    §5.2 : vision rapide de l'activité production. Filtres optionnels
    en query params : date (AAAA-MM-JJ), produit (id article), equipe.
    Accessible à tout profil authentifié (le tableau de bord Direction,
    §12 du cahier des charges, viendra le consommer aussi).
    """
    from django.db.models import Count
    from .models import OrdreFabrication, StatutOF, BesoinMatierePrevu

    of_qs = OrdreFabrication.objects.all()
    date_filtre = request.query_params.get("date")
    produit_filtre = request.query_params.get("produit")
    equipe_filtre = request.query_params.get("equipe")
    if date_filtre:
        of_qs = of_qs.filter(date_creation__date=date_filtre)
    if produit_filtre:
        of_qs = of_qs.filter(article_id=produit_filtre)
    if equipe_filtre:
        of_qs = of_qs.filter(equipe=equipe_filtre)

    comptage = dict(of_qs.values_list("statut").annotate(total=Count("id")))

    # Matières manquantes : tous les BesoinMatierePrevu dont la situation est "Insuffisant"
    matieres_manquantes = []
    for besoin in BesoinMatierePrevu.objects.select_related("matiere", "ordre_fabrication").filter(
        ordre_fabrication__in=of_qs.exclude(statut__in=[StatutOF.CLOTURE, StatutOF.ANNULE])
    ):
        if besoin.situation() == "Insuffisant":
            matieres_manquantes.append({
                "of": besoin.ordre_fabrication.numero,
                "matiere": besoin.matiere.code,
                "manquant": besoin.manquant(),
            })

    # Alertes qualité : lots en attente ou bloqués (voir apps.qualite)
    from apps.qualite.models import Lot
    alertes_qualite = list(
        Lot.objects.filter(statut__in=["EN_ATTENTE", "NON_CONFORME", "BLOQUE"])
        .values("numero_lot", "statut", "article__code")
    )

    return Response({
        "of_prevus": comptage.get(StatutOF.BROUILLON, 0) + comptage.get(StatutOF.A_PREPARER, 0),
        "of_a_preparer": comptage.get(StatutOF.A_PREPARER, 0),
        "of_prets": comptage.get(StatutOF.PRET, 0),
        "of_en_cours": comptage.get(StatutOF.EN_PRODUCTION, 0),
        "of_termines": comptage.get(StatutOF.PRODUCTION_TERMINEE, 0) + comptage.get(StatutOF.EN_CONTROLE, 0),
        "of_a_cloturer": comptage.get(StatutOF.EN_CONTROLE, 0),
        "of_bloques": comptage.get(StatutOF.ANNULE, 0),
        "detail_par_statut": comptage,
        "matieres_manquantes": matieres_manquantes,
        "alertes_qualite": alertes_qualite,
    })