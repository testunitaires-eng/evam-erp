"""
Vues du socle industriel. Paramétrage par l'Administrateur SI (et la
Direction) ; lecture pour les profils qui s'en servent au quotidien.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.comptes.models import Profil
from apps.comptes.permissions import acces
from apps.core.views import HistoriqueMixin
from . import models, serializers

LECTEURS = (
    Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.MAGASINIER, Profil.RESPONSABLE_QUALITE,
    Profil.RESPONSABLE_ACHATS, Profil.COMPTABILITE_DAF, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMMERCIAL,
)
PARAMETRAGE = acces(lecture=LECTEURS, ecriture=(Profil.ADMIN_SI, Profil.DIRECTION))


class ActiviteViewSet(viewsets.ModelViewSet):
    queryset = models.Activite.objects.all()
    serializer_class = serializers.ActiviteSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["actif"]


class UsineViewSet(viewsets.ModelViewSet):
    queryset = models.Usine.objects.prefetch_related("activites")
    serializer_class = serializers.UsineSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["actif", "activites"]


class EtapeStandardViewSet(viewsets.ModelViewSet):
    queryset = models.EtapeStandard.objects.all()
    serializer_class = serializers.EtapeStandardSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["phase", "actif", "sous_etape_de"]


class LigneViewSet(viewsets.ModelViewSet):
    queryset = models.Ligne.objects.select_related("usine", "activite")
    serializer_class = serializers.LigneSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["usine", "activite", "actif"]
    search_fields = ["code", "designation"]

    @action(detail=False, methods=["get"])
    def compatibles(self, request):
        """GET .../lignes/compatibles/?article=<id> : lignes actives pouvant produire ce format (choix à la création d'un OF)."""
        from apps.referentiel.models import Article
        article = Article.objects.filter(pk=request.query_params.get("article")).first()
        if article is None:
            return Response({"erreur": "Paramètre « article » manquant ou inconnu."}, status=400)
        lignes = [ligne for ligne in self.get_queryset().filter(actif=True) if ligne.accepte(article)]
        return Response(self.get_serializer(lignes, many=True).data)


class PosteViewSet(viewsets.ModelViewSet):
    queryset = models.Poste.objects.select_related("ligne", "etape")
    serializer_class = serializers.PosteSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["ligne", "etape", "actif"]


class EquipementViewSet(viewsets.ModelViewSet):
    queryset = models.Equipement.objects.select_related("usine", "poste", "activite")
    serializer_class = serializers.EquipementSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["usine", "poste", "activite", "type_equipement", "actif"]
    search_fields = ["code", "designation"]


class CircuitViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.Circuit.objects.prefetch_related("etapes__etape")
    serializer_class = serializers.CircuitSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["activite", "article", "ligne", "statut"]

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """POST .../circuits/{id}/valider/ : Brouillon -> Validé (la version précédente est archivée)."""
        circuit = self.get_object()
        try:
            circuit.valider(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(circuit).data)

    @action(detail=True, methods=["post"])
    def nouvelle_version(self, request, pk=None):
        """POST .../circuits/{id}/nouvelle_version/ : copie modifiable (brouillon) du circuit."""
        copie = self.get_object().nouvelle_version(request.user)
        return Response(self.get_serializer(copie).data, status=201)

    @action(detail=False, methods=["get"])
    def applicable(self, request):
        """GET .../circuits/applicable/?article=<id>&ligne=<id> : circuit que recevrait un OF."""
        from apps.referentiel.models import Article
        article = Article.objects.filter(pk=request.query_params.get("article")).first()
        if article is None:
            return Response({"erreur": "Paramètre « article » manquant ou inconnu."}, status=400)
        ligne = models.Ligne.objects.filter(pk=request.query_params.get("ligne")).first()
        circuit = models.circuit_pour(article, ligne)
        return Response(self.get_serializer(circuit).data if circuit else None)


class EtapeCircuitViewSet(viewsets.ModelViewSet):
    queryset = models.EtapeCircuit.objects.select_related("etape", "circuit")
    serializer_class = serializers.EtapeCircuitSerializer
    permission_classes = [PARAMETRAGE]
    filterset_fields = ["circuit", "etape"]
