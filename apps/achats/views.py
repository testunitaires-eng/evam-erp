"""
Vues du module achats.

Droits gérés par la matrice (module ACHATS). Le Responsable Achat
pilote l'essentiel ; le Magasinier a des droits partagés sur les
réceptions et retours (cohérent avec son rôle physique).
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import droit_matrice, a_le_droit
from apps.comptes.models import Module


class FournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.Fournisseur.objects.all()
    serializer_class = serializers.FournisseurSerializer
    permission_classes = [droit_matrice(Module.ACHATS)]
    filterset_fields = ["actif"]
    search_fields = ["code", "nom"]

    def perform_create(self, serializer):
        serializer.save(gere_par=self.request.user)


class ContratFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.ContratFournisseur.objects.all()
    serializer_class = serializers.ContratFournisseurSerializer
    permission_classes = [droit_matrice(Module.ACHATS)]
    filterset_fields = ["fournisseur", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(gere_par=self.request.user)


class ArticleFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.ArticleFournisseur.objects.all()
    serializer_class = serializers.ArticleFournisseurSerializer
    permission_classes = [droit_matrice(Module.ACHATS)]
    filterset_fields = ["fournisseur", "article", "contrat"]


class BesoinApprovisionnementViewSet(viewsets.ModelViewSet):
    queryset = models.BesoinApprovisionnement.objects.all()
    serializer_class = serializers.BesoinApprovisionnementSerializer
    permission_classes = [droit_matrice(Module.ACHATS)]
    filterset_fields = ["article", "origine", "satisfait"]


class DemandeAchatViewSet(viewsets.ModelViewSet):
    queryset = models.DemandeAchat.objects.all()
    serializer_class = serializers.DemandeAchatSerializer
    permission_classes = [droit_matrice(Module.ACHATS)]
    filterset_fields = ["article", "statut", "demandeur"]

    def perform_create(self, serializer):
        serializer.save(demandeur=self.request.user)

    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):
        """POST /api/achats/demandes/{id}/approuver/ - nécessite peut_valider=True sur ACHATS."""
        if not a_le_droit(request.user, Module.ACHATS, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas approuver une demande d'achat."}, status=403)
        demande = self.get_object()
        demande.approuver(request.user)
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        """POST /api/achats/demandes/{id}/rejeter/ - nécessite peut_valider=True sur ACHATS."""
        if not a_le_droit(request.user, Module.ACHATS, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas rejeter une demande d'achat."}, status=403)
        demande = self.get_object()
        demande.rejeter(request.user)
        return Response(self.get_serializer(demande).data)


class CommandeFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.CommandeFournisseur.objects.all()
    serializer_class = serializers.CommandeFournisseurSerializer
    permission_classes = [droit_matrice(Module.ACHATS)]
    filterset_fields = ["fournisseur", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def envoyer(self, request, pk=None):
        """POST /api/achats/commandes/{id}/envoyer/ - nécessite peut_valider=True sur ACHATS."""
        if not a_le_droit(request.user, Module.ACHATS, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas envoyer une commande fournisseur."}, status=403)
        commande = self.get_object()
        try:
            commande.envoyer()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(commande).data)


class LigneCommandeFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.LigneCommandeFournisseur.objects.all()
    serializer_class = serializers.LigneCommandeFournisseurSerializer
    permission_classes = [droit_matrice(Module.ACHATS)]
    filterset_fields = ["commande", "article"]


class ReceptionAchatViewSet(viewsets.ModelViewSet):
    """
    Le Magasinier n'a pas peut_creer/peut_modifier sur ACHATS (réservés
    au Responsable Achat pour fournisseurs/contrats/commandes) : on
    réutilise donc peut_valider, que le Magasinier possède
    spécifiquement pour réceptionner, sans lui donner accès au reste
    du module.
    """
    queryset = models.ReceptionAchat.objects.all()
    serializer_class = serializers.ReceptionAchatSerializer
    permission_classes = [droit_matrice(Module.ACHATS, actions_supplementaires={
        "create": "peut_valider", "update": "peut_valider", "partial_update": "peut_valider",
    })]
    filterset_fields = ["commande", "conforme"]

    def perform_create(self, serializer):
        serializer.save(receptionne_par=self.request.user)


class LigneReceptionAchatViewSet(viewsets.ModelViewSet):
    queryset = models.LigneReceptionAchat.objects.all()
    serializer_class = serializers.LigneReceptionAchatSerializer
    permission_classes = [droit_matrice(Module.ACHATS, actions_supplementaires={
        "create": "peut_valider", "update": "peut_valider", "partial_update": "peut_valider",
    })]
    filterset_fields = ["reception", "ligne_commande"]

    def perform_create(self, serializer):
        """Met à jour automatiquement la quantité reçue de la ligne de commande et le statut de la commande."""
        ligne = serializer.save()
        ligne_commande = ligne.ligne_commande
        ligne_commande.quantite_recue += ligne.quantite_recue
        ligne_commande.save()

        commande = ligne_commande.commande
        total_commande = sum(l.quantite_commandee for l in commande.lignes.all())
        total_recu = sum(l.quantite_recue for l in commande.lignes.all())
        commande.statut = "RECUE" if total_recu >= total_commande else "PARTIELLEMENT_RECUE"
        commande.save()


class RetourFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.RetourFournisseur.objects.all()
    serializer_class = serializers.RetourFournisseurSerializer
    permission_classes = [droit_matrice(Module.ACHATS, actions_supplementaires={
        "create": "peut_valider", "update": "peut_valider", "partial_update": "peut_valider",
    })]
    filterset_fields = ["reception", "article", "motif"]

    def perform_create(self, serializer):
        serializer.save(traite_par=self.request.user)
