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
