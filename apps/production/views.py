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

from django.db.models import Sum
from rest_framework import viewsets
from apps.core.views import HistoriqueMixin
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from apps.core.validation import METHODES_CREATION_LECTURE
from . import models, serializers
from apps.comptes.permissions import role_required, acces
from apps.comptes.models import Profil
from apps.comptes.permissions import role_required, lecture_seule_pour


def est_agent(utilisateur):
    return utilisateur.profil == Profil.AGENT_PRODUCTION and not utilisateur.is_superuser


class AffectationAgentMixin:
    """
    Règles de l'Agent Production (scénarios par rôle, §4) sur ses saisies :
    - il ne voit que les données de SES OF (ceux où il est affecté) ;
    - il ne saisit que sur un OF affecté ET « En production » ;
    - il crée ses saisies mais ne les modifie ni ne les supprime :
      les corrections sont faites par le Responsable Production.
    Chaque saisie est tracée (saisi_par / agent / demandeur).
    """

    def get_queryset(self):
        queryset = super().get_queryset()
        if est_agent(self.request.user):
            return queryset.filter(ordre_fabrication__agents_affectes=self.request.user)
        return queryset

    def verifier_affectation(self, of):
        if not est_agent(self.request.user):
            return
        if not of.agents_affectes.filter(pk=self.request.user.pk).exists():
            raise PermissionDenied(f"Vous n'êtes pas affecté à l'OF {of.numero}.")
        if of.statut != models.StatutOF.EN_PRODUCTION:
            raise PermissionDenied(
                f"L'OF {of.numero} est « {of.get_statut_display()} » : vous ne pouvez saisir que sur un OF en production."
            )

    def perform_create(self, serializer):
        self.verifier_affectation(serializer.validated_data["ordre_fabrication"])
        champs = {f.name for f in serializer.Meta.model._meta.fields}
        if "saisi_par" in champs:
            serializer.save(saisi_par=self.request.user)
        else:
            super().perform_create(serializer)

    def perform_update(self, serializer):
        if est_agent(self.request.user):
            raise PermissionDenied("Un Agent Production ne modifie pas une saisie : demandez la correction au Responsable Production.")
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if est_agent(self.request.user):
            raise PermissionDenied("Un Agent Production ne supprime pas une saisie : demandez la correction au Responsable Production.")
        super().perform_destroy(instance)


class PlanProductionViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.PlanProduction.objects.all()
    serializer_class = serializers.PlanProductionSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI,),
    )]
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
        from apps.comptes.models import Utilisateur
        plan = self.get_object()
        identifiants = request.data.get("agents_affectes") or []
        agents = list(Utilisateur.objects.filter(pk__in=identifiants))
        if len(agents) != len(set(identifiants)):
            return Response({"erreur": "Un ou plusieurs agents sont introuvables."}, status=400)
        try:
            of = plan.convertir_en_of(responsable=request.user, agents=agents)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(serializers.OrdreFabricationSerializer(of).data, status=201)


# class OrdreFabricationViewSet(viewsets.ModelViewSet):
#     queryset = models.OrdreFabrication.objects.all()
#     serializer_class = serializers.OrdreFabricationSerializer
#     permission_classes = [role_required(
#         Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,
#     )]
#     filterset_fields = ["article", "statut"]

class OrdreFabricationViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    # Préchargement : la liste des OF (étapes prévues, agents, contexte) se
    # charge en un nombre fixe de requêtes, quel que soit le nombre d'OF.
    queryset = models.OrdreFabrication.objects.select_related(
        "article__activite", "ligne__usine", "circuit", "responsable",
    ).prefetch_related(
        "agents_affectes", "etapes", "formats_supplementaires__article",
        "circuit__etapes__etape", "circuit__etapes__poste", "circuit__etapes__equipement",
    ).annotate(montant_besoins_annote=Sum("besoins_matieres__montant"))
    serializer_class = serializers.OrdreFabricationSerializer
    # L'Agent Production consulte ses OF (lecture seule, filtrés ci-dessous) ;
    # seuls le Responsable Production et l'Admin SI les gèrent.
    # La DAF lit les OF pour leur rattacher une charge directe (coûts en cascade).
    permission_classes = [acces(
        lecture=(Profil.AGENT_PRODUCTION, Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["article", "statut", "ligne", "circuit"]
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
        agents = serializer.validated_data.pop("agents_affectes", [])
        of = serializer.save(responsable=self.request.user)
        if agents:
            of.affecter_agents(agents, par=self.request.user)

    def perform_update(self, serializer):
        agents = serializer.validated_data.pop("agents_affectes", None)
        of = serializer.save()
        if agents is not None:
            of.affecter_agents(agents, par=self.request.user)

    @action(detail=False, methods=["get"])
    def agents_disponibles(self, request):
        """
        GET /api/production/ordres-fabrication/agents_disponibles/
        Liste de choix des agents : comptes Agent Production actifs (id, nom d'utilisateur, nom).
        """
        from apps.comptes.models import Utilisateur
        agents = Utilisateur.objects.filter(profil=Profil.AGENT_PRODUCTION, is_active=True).order_by("username")
        return Response([
            {"id": agent.pk, "username": agent.username, "nom": serializers.nom_utilisateur(agent)}
            for agent in agents
        ])

    @action(detail=True, methods=["post"])
    def affecter_agents(self, request, pk=None):
        """
        POST /api/production/ordres-fabrication/{id}/affecter_agents/
        Corps : {"agents": [<id>, ...]} (remplace la liste). Réservé au
        Responsable Production. Tracé dans le journal des actions.
        """
        if request.user.profil not in (Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Production affecte les agents à un OF."}, status=403)
        from apps.comptes.models import Utilisateur
        identifiants = request.data.get("agents")
        if not isinstance(identifiants, list):
            return Response({"erreur": "Envoyez « agents » : une liste d'identifiants (liste vide pour tout retirer)."}, status=400)
        agents = list(Utilisateur.objects.filter(pk__in=identifiants))
        if len(agents) != len(set(identifiants)):
            return Response({"erreur": "Un ou plusieurs agents sont introuvables."}, status=400)
        of = self.get_object()
        of.affecter_agents(agents, par=request.user)
        return Response(self.get_serializer(of).data)

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

    @action(detail=True, methods=["post"])
    def demander_matieres(self, request, pk=None):
        """
        POST /api/production/ordres-fabrication/{id}/demander_matieres/
        Réservé au Responsable Production. Demande au magasin toute la
        composition de l'OF (une demande par matière de la fiche).
        """
        if request.user.profil not in (Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Production peut demander les matières d'un OF."}, status=403)
        of = self.get_object()
        try:
            demandes = of.demander_matieres(demandeur=request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(serializers.DemandeMatiereSerializer(demandes, many=True).data, status=201)

    @action(detail=True, methods=["get"])
    def verifier_stock(self, request, pk=None):
        """
        GET .../ordres-fabrication/{id}/verifier_stock/
        Contrôle avant lancement : besoins de l'OF face au stock disponible
        du magasin matières de son usine. Le lancement est bloqué s'il manque
        quelque chose (selon le paramètre de production).
        """
        of = self.get_object()
        manques = of.verifier_stock_pour_lancement()
        return Response({
            "magasin": of.depot_matieres.nom, "lancement_possible": not manques,
            "blocage_actif": models.ParametreProduction.courant().bloquer_lancement_stock_insuffisant,
            "manques": manques,
        })

    @action(detail=True, methods=["get"])
    def blocages_qualite(self, request, pk=None):
        """
        GET .../ordres-fabrication/{id}/blocages_qualite/
        Ce qui empêche la clôture : contrôles bloquants non réalisés et
        non-conformités bloquantes ouvertes (liste vide = clôture possible).
        """
        from apps.qualite.models import blocages_qualite_of
        of = self.get_object()
        blocages = blocages_qualite_of(of)
        return Response({"of": of.numero, "cloture_possible": not blocages, "blocages": blocages})

    @action(detail=True, methods=["get"])
    def bon_de_sortie(self, request, pk=None):
        """GET .../ordres-fabrication/{id}/bon_de_sortie/ : bon de sortie des matières (à imprimer pour le magasin)."""
        of = self.get_object()
        return Response({
            "of": of.numero, "article": of.article.code, "designation": of.article.designation,
            "quantite_a_produire": of.quantite_a_produire, "magasin": of.depot_matieres.nom,
            "ligne": of.ligne.code if of.ligne_id else None,
            "recette": f"v{of.fiche_technique.version}" if of.fiche_technique_id else None,
            "lignes": [
                {"matiere": b.matiere.code, "designation": b.matiere.designation, "unite": b.matiere.unite_mesure,
                 "quantite": b.quantite_theorique,
                 "deja_sorti": sum(s.quantite_sortie for s in of.sorties_matieres.filter(matiere=b.matiere))}
                for b in of.besoins_matieres.select_related("matiere")
            ],
        })

    @action(detail=True, methods=["get"])
    def lots_consommes(self, request, pk=None):
        """GET .../ordres-fabrication/{id}/lots_consommes/ : lots de matières utilisés par l'OF (traçabilité amont)."""
        of = self.get_object()
        consommations = models.ConsommationLotMatiere.objects.filter(sortie__ordre_fabrication=of).select_related(
            "lot__article", "sortie__ordre_fabrication",
        )
        return Response(serializers.ConsommationLotMatiereSerializer(consommations, many=True).data)

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
        from apps.qualite.models import blocages_qualite_of
        return Response({
            "numero": of.numero,
            "statut": of.statut,
            "quantite_prevue": of.quantite_a_produire,
            "consommation_matieres": consommation,
            "suivi_eau": suivi_eau,
            "volume_eau": of.volume_eau(),
            "pertes": serializers.PerteProductionSerializer(of.pertes.all(), many=True, context={"request": request}).data,
            "changements_serie": serializers.ChangementSerieSerializer(
                of.changements_serie.all(), many=True, context={"request": request},
            ).data,
            "blocages_qualite": blocages_qualite_of(of),
        })

    @action(detail=True, methods=["get"], url_path="bon-de-sortie-pdf")
    def bon_de_sortie_pdf(self, request, pk=None):
        """GET /api/production/ordres-fabrication/{id}/bon-de-sortie-pdf/ : document PDF à imprimer (?telecharger=1 pour le télécharger)."""
        from apps.core import documents
        from apps.core.pdf import telecharger
        objet = self.get_object()
        return documents.bon_sortie(objet, request.user).reponse(f"bon-sortie-{objet.numero}", telecharger(request))


class BesoinMatierePrevuViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture seule : calculé automatiquement à la création de l'OF.
    L'Agent Production consulte les besoins de SES OF uniquement (ceux où
    il est affecté) ; aucune donnée financière n'y figure.
    """
    queryset = models.BesoinMatierePrevu.objects.select_related("ordre_fabrication", "matiere").order_by("id")
    serializer_class = serializers.BesoinMatierePrevuSerializer
    permission_classes = [acces(
        lecture=(
            Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI, Profil.DIRECTION,
            Profil.AGENT_PRODUCTION,
        ),
        ecriture=(),
    )]
    filterset_fields = ["ordre_fabrication", "matiere"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if est_agent(self.request.user):
            return queryset.filter(ordre_fabrication__agents_affectes=self.request.user)
        return queryset

    def list(self, request, *args, **kwargs):
        """Ajoute stock_disponible / manquant / situation (§5.5) à chaque ligne, sans les stocker en base."""
        # Calculés sur les objets de LA page renvoyée (et non sur le début de la liste).
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        objets = page if page is not None else list(self.filter_queryset(self.get_queryset()))
        donnees = self.get_serializer(objets, many=True).data
        for item, obj in zip(donnees, objets):
            item["stock_disponible"] = obj.stock_disponible()
            item["manquant"] = obj.manquant()
            item["situation"] = obj.situation()
        return self.get_paginated_response(donnees) if page is not None else Response(donnees)


class DemandeMatiereViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.DemandeMatiere.objects.all()
    serializer_class = serializers.DemandeMatiereSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication", "matiere", "statut"]
    search_fields = ["numero"]

    def create(self, request, *args, **kwargs):
        """
        Pas de saisie matière par matière : toute la composition de l'OF
        est demandée d'un coup via l'action demander_matieres de l'OF.
        """
        return Response({"erreur": (
            "Les matières d'un OF se demandent toutes ensemble, à partir de sa fiche de composition : "
            "POST /api/production/ordres-fabrication/{id}/demander_matieres/. "
            "Pour un besoin supplémentaire, utilisez une demande complémentaire."
        )}, status=400)

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


class DemandeComplementaireViewSet(HistoriqueMixin, AffectationAgentMixin, viewsets.ModelViewSet):
    queryset = models.DemandeComplementaire.objects.all()
    serializer_class = serializers.DemandeComplementaireSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication", "matiere", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        self.verifier_affectation(serializer.validated_data["ordre_fabrication"])
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
        try:
            demande.rejeter()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(demande).data)


# class SortieMatiereViewSet(viewsets.ModelViewSet):
#     queryset = models.SortieMatiere.objects.all()
#     serializer_class = serializers.SortieMatiereSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
#     filterset_fields = ["ordre_fabrication", "matiere", "type_sortie"]
class SortieMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.SortieMatiere.objects.all()
    serializer_class = serializers.SortieMatiereSerializer
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.DIRECTION,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication", "matiere", "type_sortie"]
    # Toutes les règles (OF verrouillé, motif, quantité, stock disponible)
    # sont vérifiées AVANT l'enregistrement (SortieMatiere.clean() +
    # MouvementStock.clean()). Une sortie ne se modifie ni ne se supprime :
    # le stock a déjà été mouvementé (faire un retour matière).
    http_method_names = METHODES_CREATION_LECTURE


# class RetourMatiereViewSet(viewsets.ModelViewSet):
#     queryset = models.RetourMatiere.objects.all()
#     serializer_class = serializers.RetourMatiereSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, Profil.ADMIN_SI)]
#     filterset_fields = ["ordre_fabrication", "matiere"]
class RetourMatiereViewSet(viewsets.ModelViewSet):
    queryset = models.RetourMatiere.objects.all()
    serializer_class = serializers.RetourMatiereSerializer
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.DIRECTION,),
        ecriture=(Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication", "matiere"]
    # Un retour ne se modifie ni ne se supprime (le stock a déjà été mouvementé).
    http_method_names = METHODES_CREATION_LECTURE

class SuiviProductionViewSet(AffectationAgentMixin, viewsets.ModelViewSet):
    queryset = models.SuiviProduction.objects.all()
    serializer_class = serializers.SuiviProductionSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,),
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


class SuiviEauViewSet(AffectationAgentMixin, viewsets.ModelViewSet):
    queryset = models.SuiviEau.objects.all()
    serializer_class = serializers.SuiviEauSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication"]


class EtapeProductionViewSet(AffectationAgentMixin, viewsets.ModelViewSet):
    queryset = models.EtapeProduction.objects.all()
    serializer_class = serializers.EtapeProductionSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,),
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
        self.verifier_affectation(serializer.validated_data["ordre_fabrication"])
        serializer.save(agent=self.request.user)   # l'agent de l'étape = celui qui la saisit


class PerteProductionViewSet(AffectationAgentMixin, viewsets.ModelViewSet):
    queryset = models.PerteProduction.objects.all()
    serializer_class = serializers.PerteProductionSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,),
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
@drf_permission_classes([acces(lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI,))])
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
    if est_agent(request.user):
        of_qs = of_qs.filter(agents_affectes=request.user)
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



class ChangementSerieViewSet(AffectationAgentMixin, viewsets.ModelViewSet):
    """Changements de série (temps d'arrêt, nettoyage, réglage, essais, rebuts de démarrage)."""
    queryset = models.ChangementSerie.objects.select_related("ordre_fabrication")
    serializer_class = serializers.ChangementSerieSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication", "ligne"]


class ParametreProductionViewSet(viewsets.GenericViewSet):
    """GET /api/production/parametres/ et PATCH /api/production/parametres/modifier/ : règles de production (une seule fiche)."""
    queryset = models.ParametreProduction.objects.all()
    serializer_class = serializers.ParametreProductionSerializer
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_QUALITE, Profil.DIRECTION,),
        ecriture=(Profil.ADMIN_SI, Profil.DIRECTION,),
    )]

    def list(self, request):
        return Response(self.get_serializer(models.ParametreProduction.courant()).data)

    @action(detail=False, methods=["patch"], url_path="modifier")
    def modifier(self, request):
        serializer = self.get_serializer(models.ParametreProduction.courant(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class EvenementProductionViewSet(AffectationAgentMixin, viewsets.ModelViewSet):
    """Cuve préparée, nettoyage / désinfection, arrêt puis redémarrage : déclenchent les contrôles prévus au plan."""
    queryset = models.EvenementProduction.objects.select_related("ordre_fabrication", "equipement")
    serializer_class = serializers.EvenementProductionSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication", "type_evenement", "equipement"]


class FormatOFViewSet(viewsets.ModelViewSet):
    """Formats supplémentaires d'un OF (modifiables tant que l'OF est en brouillon ; besoins recalculés)."""
    queryset = models.FormatOF.objects.select_related("article", "ordre_fabrication")
    serializer_class = serializers.FormatOFSerializer
    permission_classes = [acces(
        lecture=(Profil.AGENT_PRODUCTION, Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["ordre_fabrication", "article"]


class ReservationMatiereViewSet(viewsets.ReadOnlyModelViewSet):
    """Matières réservées par les OF lancés (libérées à la sortie, à la clôture ou à l'annulation)."""
    queryset = models.ReservationMatiere.objects.select_related("matiere", "depot", "ordre_fabrication")
    serializer_class = serializers.ReservationMatiereSerializer
    permission_classes = [acces(lecture=(
        Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.DIRECTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,
    ))]
    filterset_fields = ["ordre_fabrication", "matiere", "depot"]


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.DIRECTION, Profil.MAGASINIER, Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI,))])
def planning(request):
    """
    GET /api/production/planning/?du=AAAA-MM-JJ&au=AAAA-MM-JJ&ligne=<id>
    Planning par ligne (Q32) : OF planifiés, heures planifiées par jour
    face à la capacité (heures de production par jour), surcharges, et OF
    non encore planifiés.
    """
    from datetime import date, datetime, time, timedelta
    from decimal import Decimal
    from django.utils import timezone
    from apps.industriel.models import Ligne
    try:
        du = date.fromisoformat(request.query_params.get("du") or timezone.localdate().isoformat())
        au = date.fromisoformat(request.query_params.get("au") or (du + timedelta(days=6)).isoformat())
    except ValueError:
        return Response({"erreur": "Dates au format AAAA-MM-JJ."}, status=400)
    if au < du or (au - du).days > 92:
        return Response({"erreur": "Période invalide (93 jours au plus)."}, status=400)
    capacite = models.ParametreProduction.courant().heures_ouvrees_par_jour
    debut = timezone.make_aware(datetime.combine(du, time.min))
    fin = timezone.make_aware(datetime.combine(au + timedelta(days=1), time.min))
    lignes = Ligne.objects.filter(actif=True).select_related("usine", "activite")
    if request.query_params.get("ligne"):
        lignes = lignes.filter(pk=request.query_params["ligne"])
    actifs = models.OrdreFabrication.objects.exclude(statut__in=(models.StatutOF.CLOTURE, models.StatutOF.ANNULE))
    resultat = []
    for ligne in lignes:
        ofs = list(actifs.filter(ligne=ligne, date_debut_prevue__lt=fin, date_fin_prevue__gt=debut)
                   .select_related("article").order_by("date_debut_prevue"))
        jours = []
        jour = du
        while jour <= au:
            debut_jour = timezone.make_aware(datetime.combine(jour, time.min))
            fin_jour = debut_jour + timedelta(days=1)
            heures = Decimal(0)
            for of in ofs:
                chevauchement = min(of.date_fin_prevue, fin_jour) - max(of.date_debut_prevue, debut_jour)
                if chevauchement.total_seconds() > 0:
                    heures += Decimal(chevauchement.total_seconds()) / Decimal(3600)
            charge = min(heures, Decimal(24))
            jours.append({"date": jour, "heures_planifiees": round(charge, 2), "capacite_heures": capacite,
                          "taux_charge": round(charge / capacite * 100, 1) if capacite else None,
                          "surcharge": charge > capacite})
            jour += timedelta(days=1)
        resultat.append({
            "ligne": ligne.code, "designation": ligne.designation, "usine": ligne.usine.code, "activite": ligne.activite.code,
            "cadence": ligne.cadence_nominale, "unite_cadence": ligne.unite_cadence,
            "ordres_fabrication": [
                {"id": of.pk, "numero": of.numero, "article": of.article.code, "quantite": of.quantite_a_produire,
                 "statut": of.get_statut_display(), "debut": of.date_debut_prevue, "fin": of.date_fin_prevue}
                for of in ofs
            ],
            "jours": jours,
        })
    non_planifies = actifs.filter(date_debut_prevue__isnull=True).select_related("article", "ligne")
    return Response({
        "du": du, "au": au, "lignes": resultat,
        "of_non_planifies": [
            {"id": of.pk, "numero": of.numero, "article": of.article.code, "quantite": of.quantite_a_produire,
             "ligne": of.ligne.code if of.ligne_id else None, "statut": of.get_statut_display()}
            for of in non_planifies
        ],
    })


class DonneeObligatoireEtapeViewSet(viewsets.ModelViewSet):
    """Q33 : données à saisir par étape, obligatoires ou facultatives (paramétrage avec les techniciens)."""
    queryset = models.DonneeObligatoireEtape.objects.select_related("etape")
    serializer_class = serializers.DonneeObligatoireEtapeSerializer
    permission_classes = [acces(
        lecture=(Profil.AGENT_PRODUCTION, Profil.RESPONSABLE_QUALITE, Profil.DIRECTION,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["etape", "obligatoire"]
