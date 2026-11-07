"""
Vues du module achats.

Le Responsable Achat pilote l'intégralité du module : fournisseurs,
contrats, catalogue, demandes, commandes. Le Magasinier reste
responsable de la réception PHYSIQUE et des retours (cohérent avec
son rôle dans les autres modules), mais ne peut pas créer/gérer de
fournisseur, contrat ou commande.
"""

from rest_framework import viewsets
from apps.core.views import HistoriqueMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.validation import METHODES_CREATION_LECTURE
from . import models, serializers
from apps.comptes.permissions import acces
from apps.comptes.models import Profil

PROFILS_ACHATS = (Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)


class FournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.Fournisseur.objects.all()
    serializer_class = serializers.FournisseurSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.MAGASINIER, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["actif"]
    search_fields = ["code", "nom"]

    def perform_create(self, serializer):
        serializer.save(gere_par=self.request.user)


class ContratFournisseurViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    """Gestion des contrats fournisseurs - exclusivement le Responsable Achat."""
    queryset = models.ContratFournisseur.objects.all()
    serializer_class = serializers.ContratFournisseurSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["fournisseur", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(gere_par=self.request.user)


class ArticleFournisseurViewSet(viewsets.ModelViewSet):
    """Le catalogue des produits fournis par chaque fournisseur, avec leur prix."""
    queryset = models.ArticleFournisseur.objects.all()
    serializer_class = serializers.ArticleFournisseurSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.MAGASINIER, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["fournisseur", "article", "contrat"]


class BesoinApprovisionnementViewSet(viewsets.ModelViewSet):
    queryset = models.BesoinApprovisionnement.objects.all()
    serializer_class = serializers.BesoinApprovisionnementSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.MAGASINIER, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["article", "origine", "satisfait", "ordres_fabrication"]

    @action(detail=True, methods=["post"])
    def creer_demande(self, request, pk=None):
        """
        POST /api/achats/besoins/{id}/creer_demande/
        Crée la demande d'achat à partir du besoin (article et quantité repris).
        """
        besoin = self.get_object()
        try:
            demande = besoin.creer_demande_achat(demandeur=request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(serializers.DemandeAchatSerializer(demande).data, status=201)


class DemandeAchatViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.DemandeAchat.objects.all()
    serializer_class = serializers.DemandeAchatSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI, Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER,),
    )]
    filterset_fields = ["article", "statut", "demandeur"]

    def perform_create(self, serializer):
        serializer.save(demandeur=self.request.user)

    @staticmethod
    def _peut_traiter(utilisateur):
        """Approuver/rejeter : Responsable Achat, ou Administrateur SI (accès total)."""
        return utilisateur.is_superuser or utilisateur.profil in PROFILS_ACHATS

    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):
        """POST /api/achats/demandes/{id}/approuver/ - Responsable Achat ou Administrateur SI."""
        if not self._peut_traiter(request.user):
            return Response({"erreur": "Seul le Responsable Achat peut approuver une demande."}, status=403)
        demande = self.get_object()
        try:
            demande.approuver(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        """POST /api/achats/demandes/{id}/rejeter/ - Responsable Achat ou Administrateur SI."""
        if not self._peut_traiter(request.user):
            return Response({"erreur": "Seul le Responsable Achat peut rejeter une demande."}, status=403)
        demande = self.get_object()
        try:
            demande.rejeter(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(demande).data)


class CommandeFournisseurViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.CommandeFournisseur.objects.all()
    serializer_class = serializers.CommandeFournisseurSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.MAGASINIER, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["fournisseur", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def envoyer(self, request, pk=None):
        """POST /api/achats/commandes/{id}/envoyer/ - passe la commande de Brouillon à Envoyée."""
        commande = self.get_object()
        try:
            commande.envoyer()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(commande).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/achats/commandes/{id}/pdf/ : document PDF à imprimer (?telecharger=1 pour le télécharger)."""
        from apps.core import documents
        from apps.core.pdf import telecharger
        objet = self.get_object()
        return documents.commande_fournisseur(objet, request.user).reponse(f"bon-commande-{objet.numero}", telecharger(request))


class LigneCommandeFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.LigneCommandeFournisseur.objects.all()
    serializer_class = serializers.LigneCommandeFournisseurSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.MAGASINIER, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["commande", "article"]

class ReceptionAchatViewSet(viewsets.ModelViewSet):
    queryset = models.ReceptionAchat.objects.all()
    serializer_class = serializers.ReceptionAchatSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.MAGASINIER, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["commande", "conforme"]

    def perform_create(self, serializer):
        serializer.save(receptionne_par=self.request.user)


class LigneReceptionAchatViewSet(viewsets.ModelViewSet):
    queryset = models.LigneReceptionAchat.objects.all()
    serializer_class = serializers.LigneReceptionAchatSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.MAGASINIER, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["reception", "ligne_commande"]

    # La mise à jour de la ligne de commande, du statut de la commande et
    # l'entrée en stock sont faites par LigneReceptionAchat.save(), dans
    # une seule transaction et APRÈS contrôle (quantité <= reste à
    # recevoir, ligne appartenant bien à la commande réceptionnée...).
    # Une ligne de réception ne se modifie ni ne se supprime : le stock
    # est déjà entré.
    http_method_names = METHODES_CREATION_LECTURE


class RetourFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.RetourFournisseur.objects.all()
    serializer_class = serializers.RetourFournisseurSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.MAGASINIER, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["reception", "article", "motif"]
    # Un retour ne se modifie ni ne se supprime (le stock a déjà été sorti).
    http_method_names = METHODES_CREATION_LECTURE

    def perform_create(self, serializer):
        serializer.save(traite_par=self.request.user)
