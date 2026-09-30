"""
Vues du module comptes.

Seul l'Administrateur SI (ou un superutilisateur) peut créer/modifier
des utilisateurs. Le JournalAction est consultable par Comptabilité/
DAF et Direction (accès transversal en lecture), mais jamais
modifiable via l'API (traçabilité intègre).
"""

from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.exceptions import APIException
from django.db import transaction
from django.utils.decorators import method_decorator
from rest_framework.serializers import ModelSerializer
from . import models, serializers
from .permissions import role_required
from .models import Profil, Module


class MoiSerializer(ModelSerializer):
    """
    Sérialiseur minimal pour /api/comptes/moi/ : uniquement ce dont le
    frontend a besoin pour savoir "qui est connecté et avec quel
    profil" (id, nom, profil...). Volontairement séparé de
    UtilisateurSerializer pour ne jamais exposer de champ sensible
    sur cette route ouverte à tous les profils authentifiés.
    """
    class Meta:
        model = models.Utilisateur
        fields = ["id", "username", "first_name", "last_name", "email", "profil", "telephone", "is_active"]


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def moi(request):
    """
    GET /api/comptes/moi/

    Renvoie la fiche de l'utilisateur actuellement connecté. Si le
    compte vient d'être désactivé, cette route (comme toutes les
    autres) répond 401 AVANT même d'atteindre ce code : SimpleJWT
    vérifie is_active à chaque requête, pas seulement à la connexion.
    """
    return Response(MoiSerializer(request.user).data)


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def annuaire(request):
    """
    GET /api/comptes/annuaire/
    Noms lisibles de tous les comptes (id, identifiant, nom, profil), pour
    que chaque écran affiche « Awa Kodia » au lieu de « #12 ». Aucune
    donnée sensible (ni e-mail, ni téléphone). ?profil=... pour filtrer.
    """
    comptes = models.Utilisateur.objects.all().order_by("username")
    if request.query_params.get("profil"):
        comptes = comptes.filter(profil=request.query_params["profil"])
    return Response([
        {
            "id": compte.pk, "username": compte.username,
            "nom": compte.get_full_name() or compte.username,
            "profil": compte.profil, "profil_libelle": compte.get_profil_display(),
            "actif": compte.is_active,
        }
        for compte in comptes
    ])


class UtilisateurViewSet(viewsets.ModelViewSet):
    queryset = models.Utilisateur.objects.all()
    serializer_class = serializers.UtilisateurSerializer
    permission_classes = [role_required(Profil.ADMIN_SI)]
    filterset_fields = ["profil", "is_active"]
    search_fields = ["username", "first_name", "last_name", "email"]

    @action(detail=True, methods=["post"])
    def desactiver(self, request, pk=None):
        """
        POST /api/comptes/utilisateurs/{id}/desactiver/

        Désactive le compte. Effet immédiat : la prochaine requête de
        cet utilisateur (même avec un jeton encore valide) sera
        refusée par SimpleJWT. Trace qui a fait l'action et quand.
        """
        utilisateur_cible = self.get_object()
        if utilisateur_cible == request.user:
            return Response({"erreur": "Impossible de désactiver son propre compte."}, status=400)
        utilisateur_cible.desactiver(request.user)   # tracé par le journal automatique
        return Response(self.get_serializer(utilisateur_cible).data)

    @action(detail=True, methods=["post"])
    def activer(self, request, pk=None):
        """POST /api/comptes/utilisateurs/{id}/activer/ - réactive le compte."""
        utilisateur_cible = self.get_object()
        utilisateur_cible.activer()   # tracé par le journal automatique
        return Response(self.get_serializer(utilisateur_cible).data)


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class ConnexionJournaliseeView(TokenObtainPairView):
    """
    POST /api/auth/connexion/ - identique à SimpleJWT, mais chaque tentative
    est journalisée : connexion réussie (qui, IP) ou échec (identifiant tenté).
    Hors transaction de requête : sinon l'échec (réponse 401) annulerait
    aussi la ligne de journal qui le trace.
    """

    def post(self, request, *args, **kwargs):
        from apps.core.journal import journaliser
        identifiant = str(request.data.get("username", ""))[:150]
        try:
            reponse = super().post(request, *args, **kwargs)
        except APIException as erreur:
            journaliser(None, "Échec de connexion", nouvelle=f"Identifiant : {identifiant}", module=Module.ADMINISTRATION)
            detail = erreur.detail if isinstance(erreur.detail, dict) else {"detail": erreur.detail}
            return Response(detail, status=erreur.status_code)
        compte = models.Utilisateur.objects.filter(username=identifiant).first()
        journaliser(compte, "Connexion", utilisateur=compte, module=Module.ADMINISTRATION)
        return reponse


class JournalActionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture seule : le journal ne se modifie jamais depuis l'API.
    Filtres : ?utilisateur=<id>&module=CAISSE&document_type=caisse.decaissement
              &document_id=DEC-000012&date_debut=AAAA-MM-JJ&date_fin=AAAA-MM-JJ
    Recherche : ?search=... (action, référence, valeurs).
    """
    queryset = models.JournalAction.objects.all()
    serializer_class = serializers.JournalActionSerializer
    permission_classes = [role_required(
        Profil.ADMIN_SI, Profil.COMPTABILITE_DAF, Profil.DIRECTION,
    )]
    filterset_fields = ["module", "utilisateur", "document_type", "document_id"]
    search_fields = ["action", "document_id", "ancienne_valeur", "nouvelle_valeur"]

    def get_queryset(self):
        queryset = super().get_queryset().select_related("utilisateur")
        parametres = self.request.query_params
        if parametres.get("date_debut"):
            queryset = queryset.filter(date_action__date__gte=parametres["date_debut"])
        if parametres.get("date_fin"):
            queryset = queryset.filter(date_action__date__lte=parametres["date_fin"])
        return queryset
