"""
Vues du module caisse.

Le Caissier ne peut PAS supprimer un écart -> aucune route DELETE
n'est exposée sur EcartCaisse, il doit toujours le justifier via un
enregistrement.
"""

from django.utils.dateparse import parse_date
from rest_framework import viewsets, mixins
from apps.core.views import HistoriqueMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.core.validation import METHODES_CREATION_LECTURE
from . import models, serializers
from apps.comptes.permissions import role_required , lecture_seule_pour, acces
from apps.comptes.models import Profil, Utilisateur


# class CaisseViewSet(viewsets.ModelViewSet):
#     queryset = models.Caisse.objects.all()
#     serializer_class = serializers.CaisseSerializer
#     permission_classes = [role_required(Profil.ADMIN_SI)]

PROFILS_SUPERVISION_CAISSE = (Profil.ADMIN_SI, Profil.COMPTABILITE_DAF, Profil.DIRECTION)


def voit_toutes_les_caisses(utilisateur):
    return utilisateur.is_superuser or utilisateur.profil in PROFILS_SUPERVISION_CAISSE


class FiltreCaissierMixin:
    """Un caissier ne voit que les données de SA caisse (sessions, encaissements, décaissements)."""
    filtre_caissier = "session_caisse__caissier"

    def get_queryset(self):
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.profil == Profil.CAISSIER and not utilisateur.is_superuser:
            return queryset.filter(**{self.filtre_caissier: utilisateur})
        return queryset


class CaisseViewSet(viewsets.ModelViewSet):
    """
    Création des caisses et affectation des caissiers : Administrateur SI.
    La caisse principale est créée par le système (non supprimable).
    """
    queryset = models.Caisse.objects.all().order_by("-est_principale", "nom")
    serializer_class = serializers.CaisseSerializer
    permission_classes = [acces(
        lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.CAISSIER,),
        ecriture=(Profil.ADMIN_SI,),
    )]
    filterset_fields = ["actif", "caissier", "est_principale"]

    def get_queryset(self):
        """Un caissier ne voit que sa propre caisse (écran « Ma caisse »)."""
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.profil == Profil.CAISSIER and not utilisateur.is_superuser:
            return queryset.filter(caissier=utilisateur)
        return queryset

    @action(detail=False, methods=["get"])
    def principale(self, request):
        """
        GET /api/caisse/caisses/principale/
        Montant global et détail par caisse (caissier, session ouverte,
        solde). Réservé à l'Admin SI, la Comptabilité/DAF et la Direction.
        """
        if not voit_toutes_les_caisses(request.user):
            return Response({"erreur": "Seuls l'Admin SI, la Comptabilité/DAF et la Direction voient la caisse principale."}, status=403)
        principale = models.Caisse.principale()
        caisses = models.Caisse.objects.filter(est_principale=False).order_by("nom")
        return Response({
            "caisse": self.get_serializer(principale).data if principale else None,
            "montant_global": principale.solde_actuel if principale else sum((c.solde_propre() for c in caisses), 0),
            "caisses": [
                {
                    "id": caisse.pk, "nom": caisse.nom, "actif": caisse.actif,
                    "caissier": models.nom_utilisateur(caisse.caissier),
                    "caissier_id": caisse.caissier_id,
                    "session_ouverte": getattr(caisse.session_ouverte(), "pk", None),
                    "solde": caisse.solde_propre(),
                }
                for caisse in caisses
            ],
        })

    @action(detail=True, methods=["get"])
    def journal(self, request, pk=None):
        """
        GET /api/caisse/caisses/{id}/journal/?date_debut=AAAA-MM-JJ&date_fin=AAAA-MM-JJ&caissier=<id>
        Traçabilité : chaque entrée (encaissement) et sortie (décaissement)
        avec montant, caisse, caissier, date et heure. Sur la caisse
        principale : toutes les caisses. Un caissier ne consulte que sa caisse.
        """
        caisse = self.get_object()
        if not voit_toutes_les_caisses(request.user) and caisse.caissier_id != request.user.id:
            return Response({"erreur": "Vous ne pouvez consulter que le journal de votre propre caisse."}, status=403)
        parametres = request.query_params
        date_debut = parse_date(parametres["date_debut"]) if parametres.get("date_debut") else None
        date_fin = parse_date(parametres["date_fin"]) if parametres.get("date_fin") else None
        operations = caisse.operations(date_debut=date_debut, date_fin=date_fin, caissier=parametres.get("caissier"))
        entrees = sum((o["montant"] for o in operations if o["type"] == "ENCAISSEMENT"), 0)
        sorties = -sum((o["montant"] for o in operations if o["type"] == "DECAISSEMENT"), 0)
        return Response({
            "caisse": caisse.nom,
            "est_principale": caisse.est_principale,
            "solde_actuel": caisse.solde_actuel,
            "total_encaissements": entrees,
            "total_decaissements": sorties,
            "operations": operations,
        })

class SessionCaisseViewSet(HistoriqueMixin, FiltreCaissierMixin, viewsets.ModelViewSet):
    """
    Ouverture : POST /api/caisse/sessions/ (corps vide suffit) - la caisse
    du caissier et le solde d'ouverture sont déterminés automatiquement.
    """
    queryset = models.SessionCaisse.objects.all()
    serializer_class = serializers.SessionCaisseSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.CAISSIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF,),
    )]
    filterset_fields = ["caisse", "caissier", "statut"]
    filtre_caissier = "caissier"

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        """
        POST /api/caisse/sessions/{id}/cloturer/
        Corps : {"solde_compte": ..., "justification": "..."}
        Le solde théorique est calculé par le système. S'il y a un écart,
        "justification" est obligatoire, sinon la session reste ouverte.
        Seul le caissier de la session clôture sa caisse.
        """
        session = self.get_object()
        if session.caissier_id != request.user.id and not request.user.is_superuser:
            return Response({"erreur": "Seul le caissier de cette session peut clôturer sa caisse."}, status=403)
        try:
            session.cloturer(
                solde_compte=request.data.get("solde_compte"),
                justification=request.data.get("justification"),
            )
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response({"session": self.get_serializer(session).data})


class EncaissementViewSet(FiltreCaissierMixin, viewsets.ModelViewSet):
    queryset = models.Encaissement.objects.all()
    serializer_class = serializers.EncaissementSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.CAISSIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF,),
    )]
    filterset_fields = ["session_caisse", "facture", "mode_paiement"]
    search_fields = ["numero"]
    # Un encaissement ne se modifie ni ne se supprime (traçabilité caisse).
    http_method_names = METHODES_CREATION_LECTURE

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/caisse/encaissements/{id}/pdf/ : document PDF à imprimer (?telecharger=1 pour le télécharger)."""
        from apps.core import documents
        from apps.core.pdf import telecharger
        objet = self.get_object()
        return documents.recu_caisse(objet, request.user).reponse(f"recu-{objet.numero}", telecharger(request))


class EcartCaisseViewSet(
    mixins.CreateModelMixin, mixins.RetrieveModelMixin,
    mixins.ListModelMixin, mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Volontairement PAS de DestroyModelMixin : un écart de caisse ne se
    supprime jamais, il se justifie.
    """
    queryset = models.EcartCaisse.objects.all()
    serializer_class = serializers.EcartCaisseSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.CAISSIER, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF,),
    )]
    filterset_fields = ["session_caisse"]

    def get_queryset(self):
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if utilisateur.profil == Profil.CAISSIER and not utilisateur.is_superuser:
            return queryset.filter(session_caisse__caissier=utilisateur)
        return queryset

    def create(self, request, *args, **kwargs):
        """L'écart se justifie à la clôture de la session (action /cloturer/), pas après."""
        return Response({"erreur": (
            "Un écart se justifie au moment de la clôture : "
            "POST /api/caisse/sessions/{id}/cloturer/ avec solde_compte et justification."
        )}, status=400)





class DecaissementViewSet(HistoriqueMixin, FiltreCaissierMixin, viewsets.ModelViewSet):
    """§9.1/§9.2 : sortie de caisse autorisée, distincte d'un encaissement."""
    queryset = models.Decaissement.objects.all()
    serializer_class = serializers.DecaissementSerializer
    # Seul le caissier de la session demande (règle du modèle) : la DAF et
    # l'Admin SI consultent ; Direction et DAF décident par /autoriser/ et /refuser/.
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,),
        ecriture=(Profil.CAISSIER,),
    )]
    filterset_fields = ["session_caisse", "statut"]
    search_fields = ["numero"]
    # Une demande ne se modifie ni ne se supprime (traçabilité caisse) :
    # elle évolue uniquement par les actions autoriser / refuser / effectuer.
    http_method_names = METHODES_CREATION_LECTURE

    def perform_create(self, serializer):
        serializer.save(effectue_par=self.request.user)

    @action(detail=False, methods=["get"])
    def a_autoriser(self, request):
        """
        GET /api/caisse/decaissements/a_autoriser/
        Écran « À autoriser » de la Direction et de la Comptabilité/DAF :
        demandes en attente, les plus anciennes d'abord.
        """
        demandes = self.get_queryset().filter(
            statut=models.StatutDecaissement.EN_ATTENTE,
        ).order_by("date_decaissement")
        return Response(self.get_serializer(demandes, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[acces(ecriture=models.PROFILS_AUTORISANT_DECAISSEMENT)])
    def autoriser(self, request, pk=None):
        """POST .../autoriser/ - Direction ou Comptabilité/DAF."""
        decaissement = self.get_object()
        try:
            decaissement.autoriser(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(decaissement).data)

    @action(detail=True, methods=["post"], permission_classes=[acces(ecriture=models.PROFILS_AUTORISANT_DECAISSEMENT)])
    def refuser(self, request, pk=None):
        """POST .../refuser/  Corps : {"motif": "..."} (obligatoire) - Direction ou Comptabilité/DAF."""
        decaissement = self.get_object()
        try:
            decaissement.refuser(request.user, request.data.get("motif"))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(decaissement).data)

    @action(detail=True, methods=["post"], permission_classes=[acces(ecriture=(Profil.CAISSIER,))])
    def effectuer(self, request, pk=None):
        """POST .../effectuer/ - le caissier sort l'argent d'un décaissement AUTORISÉ."""
        decaissement = self.get_object()
        try:
            decaissement.effectuer(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(decaissement).data)

    @action(detail=False, methods=["get"])
    def autorisateurs(self, request):
        """
        GET /api/caisse/decaissements/autorisateurs/
        Liste de choix du champ « Autorisé par » : comptes actifs de la
        Direction et de la Comptabilité/DAF (id, nom d'utilisateur, nom, profil).
        """
        personnes = Utilisateur.objects.filter(
            profil__in=models.PROFILS_AUTORISANT_DECAISSEMENT, is_active=True,
        ).order_by("profil", "username")
        return Response(serializers.AutorisateurSerializer(personnes, many=True).data)
