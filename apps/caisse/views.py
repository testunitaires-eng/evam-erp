"""
Vues du module caisse.

Le Caissier ne peut PAS supprimer un écart -> aucune route DELETE
n'est exposée sur EcartCaisse (on utilise un ModelViewSet mais on
retire explicitement la méthode destroy), il doit toujours le
justifier via un enregistrement.
"""

from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required
from apps.comptes.models import Profil


class CaisseViewSet(viewsets.ModelViewSet):
    queryset = models.Caisse.objects.all()
    serializer_class = serializers.CaisseSerializer
    permission_classes = [role_required(Profil.ADMIN_SI)]


class SessionCaisseViewSet(viewsets.ModelViewSet):
    queryset = models.SessionCaisse.objects.all()
    serializer_class = serializers.SessionCaisseSerializer
    permission_classes = [role_required(Profil.CAISSIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF)]
    filterset_fields = ["caisse", "caissier", "statut"]

    def perform_create(self, serializer):
        serializer.save(caissier=self.request.user)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        """
        POST /api/caisse/sessions/{id}/cloturer/
        Corps attendu : {"solde_theorique": ..., "solde_compte": ...}
        Si un écart existe, il doit être justifié séparément via
        /api/caisse/ecarts/ (le caissier ne peut jamais le supprimer).
        """
        session = self.get_object()
        session.cloturer(
            solde_theorique=request.data.get("solde_theorique"),
            solde_compte=request.data.get("solde_compte"),
        )
        reponse = {"session": self.get_serializer(session).data}
        if session.ecart and session.ecart != 0:
            reponse["avertissement"] = (
                f"Écart de {session.ecart} détecté. "
                "Une justification est obligatoire (POST /api/caisse/ecarts/)."
            )
        return Response(reponse)


class EncaissementViewSet(viewsets.ModelViewSet):
    queryset = models.Encaissement.objects.all()
    serializer_class = serializers.EncaissementSerializer
    permission_classes = [role_required(Profil.CAISSIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF)]
    filterset_fields = ["session_caisse", "facture", "mode_paiement"]
    search_fields = ["numero"]


class EcartCaisseViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin,
    mixins.ListModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Volontairement PAS de DestroyModelMixin : un écart de caisse ne se
    supprime jamais, il se justifie (règle explicite du cahier des
    charges : "il doit le justifier").
    """
    queryset = models.EcartCaisse.objects.all()
    serializer_class = serializers.EcartCaisseSerializer
    permission_classes = [role_required(Profil.CAISSIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF)]
    filterset_fields = ["session_caisse"]
