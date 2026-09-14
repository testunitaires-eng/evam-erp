"""
Vues du module comptes.

Les droits d'écriture sur ce module (créer un utilisateur, changer la
matrice de droits) sont eux-mêmes régis par la matrice de droits, sur
le module ADMINISTRATION - configurable comme le reste, mais avec une
seule ligne cochée par défaut (ADMIN_SI) pour ne jamais se retrouver
sans personne capable d'administrer les droits.
"""

from rest_framework import viewsets
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ModelSerializer
from . import models, serializers
from .permissions import droit_matrice
from .models import Module


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


class UtilisateurViewSet(viewsets.ModelViewSet):
    queryset = models.Utilisateur.objects.all()
    serializer_class = serializers.UtilisateurSerializer
    permission_classes = [droit_matrice(Module.ADMINISTRATION)]
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
        utilisateur_cible.desactiver(request.user)
        models.JournalAction.objects.create(
            utilisateur=request.user, module=Module.ADMINISTRATION,
            action="Désactivation de compte",
            document_type="Utilisateur", document_id=str(utilisateur_cible.id),
            ancienne_valeur="actif", nouvelle_valeur="désactivé",
        )
        return Response(self.get_serializer(utilisateur_cible).data)

    @action(detail=True, methods=["post"])
    def activer(self, request, pk=None):
        """POST /api/comptes/utilisateurs/{id}/activer/ - réactive le compte."""
        utilisateur_cible = self.get_object()
        utilisateur_cible.activer()
        models.JournalAction.objects.create(
            utilisateur=request.user, module=Module.ADMINISTRATION,
            action="Réactivation de compte",
            document_type="Utilisateur", document_id=str(utilisateur_cible.id),
            ancienne_valeur="désactivé", nouvelle_valeur="actif",
        )
        return Response(self.get_serializer(utilisateur_cible).data)


class MatriceDroitViewSet(viewsets.ModelViewSet):
    queryset = models.MatriceDroit.objects.all()
    serializer_class = serializers.MatriceDroitSerializer
    permission_classes = [droit_matrice(Module.ADMINISTRATION, actions_supplementaires={
        "create": "peut_parametrer", "update": "peut_parametrer", "partial_update": "peut_parametrer",
    })]
    filterset_fields = ["profil", "module"]


class JournalActionViewSet(viewsets.ReadOnlyModelViewSet):
    """Lecture seule : le journal ne se modifie jamais depuis l'API."""
    queryset = models.JournalAction.objects.all()
    serializer_class = serializers.JournalActionSerializer
    permission_classes = [droit_matrice(Module.ADMINISTRATION)]
    filterset_fields = ["module", "utilisateur"]
    search_fields = ["action", "document_id"]
