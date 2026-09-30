"""Vues transverses partagées par les modules."""

from django.contrib.contenttypes.models import ContentType
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class HistoriqueMixin:
    """
    Ajoute GET .../{id}/historique/ à un viewset : l'onglet « Historique »
    du document (création, changements de statut : qui, quand, ancien ->
    nouveau). Passe par get_object(), donc respecte les droits et filtres
    du viewset (un caissier ne voit que l'historique de ses documents).
    """

    @action(detail=True, methods=["get"])
    def historique(self, request, pk=None):
        from .models import Historique
        from .serializers import HistoriqueSerializer
        document = self.get_object()
        lignes = Historique.objects.filter(
            content_type=ContentType.objects.get_for_model(type(document)), objet_id=document.pk,
        ).select_related("utilisateur")
        return Response(HistoriqueSerializer(lignes, many=True).data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/notifications/                 mes notifications (?lue=false pour les non lues)
    GET  /api/notifications/non_lues/        compteur de la cloche
    POST /api/notifications/{id}/lire/       marque comme lue
    POST /api/notifications/tout_lire/       tout marquer comme lu
    Chacun ne voit que SES notifications.
    """
    permission_classes = [IsAuthenticated]
    filterset_fields = ["lue", "type_document"]

    def get_serializer_class(self):
        from .serializers import NotificationSerializer
        return NotificationSerializer

    def get_queryset(self):
        from .models import Notification
        return Notification.objects.filter(destinataire=self.request.user)

    @action(detail=False, methods=["get"])
    def non_lues(self, request):
        return Response({"non_lues": self.get_queryset().filter(lue=False).count()})

    @action(detail=True, methods=["post"])
    def lire(self, request, pk=None):
        notification = self.get_object()
        notification.lue = True
        notification.save(update_fields=["lue"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"])
    def tout_lire(self, request):
        return Response({"marquees": self.get_queryset().filter(lue=False).update(lue=True)})
