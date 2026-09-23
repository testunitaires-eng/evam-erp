# """
# Vues du module achats.

# Le Responsable Achat pilote l'intégralité du module : fournisseurs,
# contrats, catalogue, demandes, commandes. Le Magasinier reste
# responsable de la réception PHYSIQUE et des retours (cohérent avec
# son rôle dans les autres modules), mais ne peut pas créer/gérer de
# fournisseur, contrat ou commande.
# """

# from rest_framework import viewsets
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from . import models, serializers
# from apps.comptes.permissions import role_required, lecture_seule_pour
# from apps.comptes.models import Profil

# PROFILS_ACHATS = (Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)
# PROFILS_LECTURE_ACHATS = (Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF, Profil.RESPONSABLE_PRODUCTION)


# class FournisseurViewSet(viewsets.ModelViewSet):
#     queryset = models.Fournisseur.objects.all()
#     serializer_class = serializers.FournisseurSerializer
#     permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
#     filterset_fields = ["actif"]
#     search_fields = ["code", "nom"]

#     def perform_create(self, serializer):
#         serializer.save(gere_par=self.request.user)


# class ContratFournisseurViewSet(viewsets.ModelViewSet):
#     """Gestion des contrats fournisseurs - exclusivement le Responsable Achat."""
#     queryset = models.ContratFournisseur.objects.all()
#     serializer_class = serializers.ContratFournisseurSerializer
#     permission_classes = [role_required(*PROFILS_ACHATS)]
#     filterset_fields = ["fournisseur", "statut"]
#     search_fields = ["numero"]

#     def perform_create(self, serializer):
#         serializer.save(gere_par=self.request.user)


# class ArticleFournisseurViewSet(viewsets.ModelViewSet):
#     """Le catalogue des produits fournis par chaque fournisseur, avec leur prix."""
#     queryset = models.ArticleFournisseur.objects.all()
#     serializer_class = serializers.ArticleFournisseurSerializer
#     permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
#     filterset_fields = ["fournisseur", "article", "contrat"]


# class BesoinApprovisionnementViewSet(viewsets.ModelViewSet):
#     queryset = models.BesoinApprovisionnement.objects.all()
#     serializer_class = serializers.BesoinApprovisionnementSerializer
#     permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
#     filterset_fields = ["article", "origine", "satisfait"]


# class DemandeAchatViewSet(viewsets.ModelViewSet):
#     queryset = models.DemandeAchat.objects.all()
#     serializer_class = serializers.DemandeAchatSerializer
#     permission_classes = [role_required(
#         *PROFILS_ACHATS, Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER,
#     )]
#     filterset_fields = ["article", "statut", "demandeur"]

#     def perform_create(self, serializer):
#         serializer.save(demandeur=self.request.user)

#     @action(detail=True, methods=["post"])
#     def approuver(self, request, pk=None):
#         """POST /api/achats/demandes/{id}/approuver/ - réservé au Responsable Achat."""
#         if request.user.profil != Profil.RESPONSABLE_ACHATS and not request.user.is_superuser:
#             return Response({"erreur": "Seul le Responsable Achat peut approuver une demande."}, status=403)
#         demande = self.get_object()
#         demande.approuver(request.user)
#         return Response(self.get_serializer(demande).data)

#     @action(detail=True, methods=["post"])
#     def rejeter(self, request, pk=None):
#         """POST /api/achats/demandes/{id}/rejeter/ - réservé au Responsable Achat."""
#         if request.user.profil != Profil.RESPONSABLE_ACHATS and not request.user.is_superuser:
#             return Response({"erreur": "Seul le Responsable Achat peut rejeter une demande."}, status=403)
#         demande = self.get_object()
#         demande.rejeter(request.user)
#         return Response(self.get_serializer(demande).data)


# class CommandeFournisseurViewSet(viewsets.ModelViewSet):
#     queryset = models.CommandeFournisseur.objects.all()
#     serializer_class = serializers.CommandeFournisseurSerializer
#     permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
#     filterset_fields = ["fournisseur", "statut"]
#     search_fields = ["numero"]

#     def perform_create(self, serializer):
#         serializer.save(cree_par=self.request.user)

#     @action(detail=True, methods=["post"])
#     def envoyer(self, request, pk=None):
#         """POST /api/achats/commandes/{id}/envoyer/ - passe la commande de Brouillon à Envoyée."""
#         commande = self.get_object()
#         try:
#             commande.envoyer()
#         except ValueError as erreur:
#             return Response({"erreur": str(erreur)}, status=400)
#         return Response(self.get_serializer(commande).data)


# # class LigneCommandeFournisseurViewSet(viewsets.ModelViewSet):
# #     queryset = models.LigneCommandeFournisseur.objects.all()
# #     serializer_class = serializers.LigneCommandeFournisseurSerializer
# #     permission_classes = [role_required(*PROFILS_ACHATS)]
# #     filterset_fields = ["commande", "article"]

# class LigneCommandeFournisseurViewSet(viewsets.ModelViewSet):
#     queryset = models.LigneCommandeFournisseur.objects.all()
#     serializer_class = serializers.LigneCommandeFournisseurSerializer
#     permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
#     filterset_fields = ["commande", "article"]

# class ReceptionAchatViewSet(viewsets.ModelViewSet):
#     queryset = models.ReceptionAchat.objects.all()
#     serializer_class = serializers.ReceptionAchatSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, *PROFILS_ACHATS)]
#     filterset_fields = ["commande", "conforme"]

#     def perform_create(self, serializer):
#         serializer.save(receptionne_par=self.request.user)


# class LigneReceptionAchatViewSet(viewsets.ModelViewSet):
#     queryset = models.LigneReceptionAchat.objects.all()
#     serializer_class = serializers.LigneReceptionAchatSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, *PROFILS_ACHATS)]
#     filterset_fields = ["reception", "ligne_commande"]

#     def perform_create(self, serializer):
#         """Met à jour automatiquement la quantité reçue de la ligne de commande et le stock."""
#         ligne = serializer.save()
#         ligne_commande = ligne.ligne_commande
#         ligne_commande.quantite_recue += ligne.quantite_recue
#         ligne_commande.save()

#         commande = ligne_commande.commande
#         total_commande = sum(l.quantite_commandee for l in commande.lignes.all())
#         total_recu = sum(l.quantite_recue for l in commande.lignes.all())
#         commande.statut = "RECUE" if total_recu >= total_commande else "PARTIELLEMENT_RECUE"
#         commande.save()


# class RetourFournisseurViewSet(viewsets.ModelViewSet):
#     queryset = models.RetourFournisseur.objects.all()
#     serializer_class = serializers.RetourFournisseurSerializer
#     permission_classes = [role_required(Profil.MAGASINIER, *PROFILS_ACHATS)]
#     filterset_fields = ["reception", "article", "motif"]

#     def perform_create(self, serializer):
#         serializer.save(traite_par=self.request.user)



"""
Vues du module achats.

Le Responsable Achat pilote l'intégralité du module : fournisseurs,
contrats, catalogue, demandes, commandes. Le Magasinier reste
responsable de la réception PHYSIQUE et des retours (cohérent avec
son rôle dans les autres modules), mais ne peut pas créer/gérer de
fournisseur, contrat ou commande.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.validation import METHODES_CREATION_LECTURE
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour
from apps.comptes.models import Profil

PROFILS_ACHATS = (Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)
PROFILS_LECTURE_ACHATS = (Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF, Profil.RESPONSABLE_PRODUCTION)


class FournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.Fournisseur.objects.all()
    serializer_class = serializers.FournisseurSerializer
    permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
    filterset_fields = ["actif"]
    search_fields = ["code", "nom"]

    def perform_create(self, serializer):
        serializer.save(gere_par=self.request.user)


class ContratFournisseurViewSet(viewsets.ModelViewSet):
    """Gestion des contrats fournisseurs - exclusivement le Responsable Achat."""
    queryset = models.ContratFournisseur.objects.all()
    serializer_class = serializers.ContratFournisseurSerializer
    permission_classes = [role_required(*PROFILS_ACHATS)]
    filterset_fields = ["fournisseur", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(gere_par=self.request.user)


class ArticleFournisseurViewSet(viewsets.ModelViewSet):
    """Le catalogue des produits fournis par chaque fournisseur, avec leur prix."""
    queryset = models.ArticleFournisseur.objects.all()
    serializer_class = serializers.ArticleFournisseurSerializer
    permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
    filterset_fields = ["fournisseur", "article", "contrat"]


class BesoinApprovisionnementViewSet(viewsets.ModelViewSet):
    queryset = models.BesoinApprovisionnement.objects.all()
    serializer_class = serializers.BesoinApprovisionnementSerializer
    permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
    filterset_fields = ["article", "origine", "satisfait"]


class DemandeAchatViewSet(viewsets.ModelViewSet):
    queryset = models.DemandeAchat.objects.all()
    serializer_class = serializers.DemandeAchatSerializer
    permission_classes = [role_required(
        *PROFILS_ACHATS, Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER,
    )]
    filterset_fields = ["article", "statut", "demandeur"]

    def perform_create(self, serializer):
        serializer.save(demandeur=self.request.user)

    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):
        """POST /api/achats/demandes/{id}/approuver/ - réservé au Responsable Achat."""
        if request.user.profil != Profil.RESPONSABLE_ACHATS and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Achat peut approuver une demande."}, status=403)
        demande = self.get_object()
        try:
            demande.approuver(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=["post"])
    def rejeter(self, request, pk=None):
        """POST /api/achats/demandes/{id}/rejeter/ - réservé au Responsable Achat."""
        if request.user.profil != Profil.RESPONSABLE_ACHATS and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Achat peut rejeter une demande."}, status=403)
        demande = self.get_object()
        try:
            demande.rejeter(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(demande).data)


class CommandeFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.CommandeFournisseur.objects.all()
    serializer_class = serializers.CommandeFournisseurSerializer
    permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
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


# class LigneCommandeFournisseurViewSet(viewsets.ModelViewSet):
#     queryset = models.LigneCommandeFournisseur.objects.all()
#     serializer_class = serializers.LigneCommandeFournisseurSerializer
#     permission_classes = [role_required(*PROFILS_ACHATS)]
#     filterset_fields = ["commande", "article"]

class LigneCommandeFournisseurViewSet(viewsets.ModelViewSet):
    queryset = models.LigneCommandeFournisseur.objects.all()
    serializer_class = serializers.LigneCommandeFournisseurSerializer
    permission_classes = [lecture_seule_pour(*PROFILS_ACHATS)]
    filterset_fields = ["commande", "article"]

class ReceptionAchatViewSet(viewsets.ModelViewSet):
    queryset = models.ReceptionAchat.objects.all()
    serializer_class = serializers.ReceptionAchatSerializer
    permission_classes = [role_required(Profil.MAGASINIER, *PROFILS_ACHATS)]
    filterset_fields = ["commande", "conforme"]

    def perform_create(self, serializer):
        serializer.save(receptionne_par=self.request.user)


class LigneReceptionAchatViewSet(viewsets.ModelViewSet):
    queryset = models.LigneReceptionAchat.objects.all()
    serializer_class = serializers.LigneReceptionAchatSerializer
    permission_classes = [role_required(Profil.MAGASINIER, *PROFILS_ACHATS)]
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
    permission_classes = [role_required(Profil.MAGASINIER, *PROFILS_ACHATS)]
    filterset_fields = ["reception", "article", "motif"]
    # Un retour ne se modifie ni ne se supprime (le stock a déjà été sorti).
    http_method_names = METHODES_CREATION_LECTURE

    def perform_create(self, serializer):
        serializer.save(traite_par=self.request.user)
