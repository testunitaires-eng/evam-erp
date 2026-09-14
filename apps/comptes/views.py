"""
Vues du module comptes.

Seul l'Administrateur SI (ou un superutilisateur) peut créer/modifier
des utilisateurs et la matrice de droits. Le JournalAction est
consultable par Comptabilité/DAF et Direction (accès transversal en
lecture), mais jamais modifiable via l'API (traçabilité intègre).
"""

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from . import models, serializers
from .permissions import role_required
from .models import Profil

class MoiSerializer(drf_serializers.ModelSerializer):
    """
    Sérialiseur minimal pour /api/comptes/moi/ : uniquement ce dont le
    frontend a besoin pour savoir "qui est connecté et avec quel
    profil" (id, nom, profil...). Volontairement séparé de
    UtilisateurSerializer pour ne jamais exposer de champ sensible
    (mot de passe haché, etc.) sur cette route ouverte à tous les
    profils authentifiés.
    """
    class Meta:
        model = models.Utilisateur
        fields = ["id", "username", "first_name", "last_name", "email", "profil", "telephone", "actif"]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def moi(request):
    """
    GET /api/comptes/moi/

    Renvoie la fiche de l'utilisateur actuellement connecté (celui du
    jeton JWT fourni). Aucune écriture, aucune donnée sur un autre
    utilisateur, aucun changement à la matrice de droits existante :
    cette route ne fait qu'exposer ce que le token contient déjà.

    Utilisée par le frontend pour résoudre le problème d'identité :
    au lieu de deviner le profil localement, il appelle cette route
    une fois après connexion et sait exactement à qui il parle.
    """
    return Response(MoiSerializer(request.user).data)



class UtilisateurViewSet(viewsets.ModelViewSet):
    queryset = models.Utilisateur.objects.all()
    serializer_class = serializers.UtilisateurSerializer
    permission_classes = [role_required(Profil.ADMIN_SI)]
    filterset_fields = ["profil", "actif"]
    search_fields = ["username", "first_name", "last_name", "email"]


class MatriceDroitViewSet(viewsets.ModelViewSet):
    queryset = models.MatriceDroit.objects.all()
    serializer_class = serializers.MatriceDroitSerializer
    permission_classes = [role_required(Profil.ADMIN_SI)]
    filterset_fields = ["profil", "module"]


class JournalActionViewSet(viewsets.ReadOnlyModelViewSet):
    """Lecture seule : le journal ne se modifie jamais depuis l'API."""
    queryset = models.JournalAction.objects.all()
    serializer_class = serializers.JournalActionSerializer
    permission_classes = [role_required(
        Profil.ADMIN_SI, Profil.COMPTABILITE_DAF, Profil.DIRECTION,
    )]
    filterset_fields = ["module", "utilisateur"]
    search_fields = ["action", "document_id"]
