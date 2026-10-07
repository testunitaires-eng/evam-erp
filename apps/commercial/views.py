"""
Vues du module commercial.

Le Commercial gère prospects/clients/contrats/tarifs/commandes/
factures. Il consulte le stock (module stocks, en lecture) mais ce
module n'expose lui-même aucune écriture sur le stock.
"""

from rest_framework import viewsets
from apps.core.views import HistoriqueMixin
from rest_framework.decorators import action, api_view, permission_classes as drf_permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from . import models, serializers
from apps.comptes.permissions import role_required, acces
from apps.comptes.models import Profil


class ClientViewSet(viewsets.ModelViewSet):
    queryset = models.Client.objects.all()
    serializer_class = serializers.ClientSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_DISTRIBUTION,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI, Profil.COMPTABILITE_DAF,),
    )]
    filterset_fields = ["type_client", "bloque"]
    search_fields = ["code", "nom"]


class ProspectViewSet(viewsets.ModelViewSet):
    queryset = models.Prospect.objects.all()
    serializer_class = serializers.ProspectSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    search_fields = ["nom"]


class ContratClientViewSet(viewsets.ModelViewSet):
    queryset = models.ContratClient.objects.all()
    serializer_class = serializers.ContratClientSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["client"]


class TarifViewSet(viewsets.ModelViewSet):
    queryset = models.Tarif.objects.all()
    serializer_class = serializers.TarifSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["article", "client"]


class CommandeViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.Commande.objects.all()
    serializer_class = serializers.CommandeSerializer
    permission_classes = [acces(
        lecture=(Profil.CAISSIER, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMPTABILITE_DAF, Profil.DIRECTION,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["client", "type_commande", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)


class DerogationPrixMixin:
    """
    POST .../{id}/autoriser_prix/ {"prix_unitaire": ..., "motif": "..."}
    Dérogation au tarif (client sous contrat uniquement), réservée à la
    Direction et à la DAF ; tracée (qui, motif, prix du tarif).
    """

    def get_permissions(self):
        if self.action == "autoriser_prix":
            return [acces(ecriture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI))()]
        return super().get_permissions()

    @action(detail=True, methods=["post"])
    def autoriser_prix(self, request, pk=None):
        from apps.core.validation import convertir_decimal
        ligne = self.get_object()
        try:
            ligne.prix_unitaire = convertir_decimal(request.data.get("prix_unitaire"), "Le prix unitaire")
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        ligne.motif_derogation = (request.data.get("motif") or "").strip()
        ligne.derogation_autorisee_par = request.user
        ligne.save()
        return Response(self.get_serializer(ligne).data)


class LigneCommandeViewSet(DerogationPrixMixin, viewsets.ModelViewSet):
    queryset = models.LigneCommande.objects.all()
    serializer_class = serializers.LigneCommandeSerializer
    permission_classes = [acces(
        lecture=(Profil.CAISSIER, Profil.RESPONSABLE_DISTRIBUTION, Profil.COMPTABILITE_DAF, Profil.DIRECTION,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["commande", "article"]


# class FactureViewSet(viewsets.ModelViewSet):
#     queryset = models.Facture.objects.all()
#     serializer_class = serializers.FactureSerializer
#     permission_classes = [role_required(
#         Profil.COMMERCIAL, Profil.CAISSIER, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,
#     )]
#     filterset_fields = ["client", "statut"]
#     search_fields = ["numero"]


class FactureViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.Facture.objects.all()
    serializer_class = serializers.FactureSerializer
    permission_classes = [acces(
        lecture=(Profil.CAISSIER, Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.RESPONSABLE_DISTRIBUTION,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["client", "statut"]
    search_fields = ["numero"]

    @action(detail=True, methods=["post"])
    def generer_lignes(self, request, pk=None):
        """
        POST /api/commercial/factures/{id}/generer_lignes/
        Génère automatiquement les lignes de facture (avec calcul et
        historisation des taxes) à partir des lignes de la commande
        liée. Échoue avec le détail de l'article en cause si un
        article de la commande n'a pas de code fiscal actif.
        """
        facture = self.get_object()
        try:
            facture.generer_lignes_depuis_commande()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(facture).data)

    @action(detail=True, methods=["get", "post"])
    def sfec(self, request, pk=None):
        """
        GET  .../factures/{id}/sfec/ : données préparées pour la facture normalisée + statut ;
        POST .../factures/{id}/sfec/ : demande la certification (refusée tant que la SFEC n'est pas activée).
        """
        from apps.fiscalite import sfec
        facture = self.get_object()
        if request.method == "POST":
            try:
                sfec.certifier(facture)
            except ValueError as erreur:
                return Response({"erreur": str(erreur)}, status=400)
        return Response({
            "statut": facture.sfec_statut, "code": facture.sfec_code, "message": facture.sfec_message,
            "donnees": sfec.donnees_facture(facture),
        })

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/commercial/factures/{id}/pdf/ : document PDF à imprimer (?telecharger=1 pour le télécharger)."""
        from apps.core import documents
        from apps.core.pdf import telecharger
        objet = self.get_object()
        return documents.facture(objet, request.user).reponse(f"facture-{objet.numero}", telecharger(request))


class LigneFactureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Lecture seule : une ligne de facture n'est jamais modifiée après
    coup (elle porte des taux fiscaux figés) - pour corriger une
    erreur, on émet un avoir (à venir), pas une modification directe.
    """
    queryset = models.LigneFacture.objects.all()
    serializer_class = serializers.LigneFactureSerializer
    permission_classes = [acces(
        lecture=(Profil.COMMERCIAL, Profil.CAISSIER, Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.RESPONSABLE_DISTRIBUTION, Profil.ADMIN_SI,),
        ecriture=(),
    )]
    filterset_fields = ["facture", "article"]





class AvoirViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.Avoir.objects.all()
    serializer_class = serializers.AvoirSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.COMMERCIAL, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["client", "statut"]
    search_fields = ["numero"]

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def utiliser(self, request, pk=None):
        """POST /api/commercial/avoirs/{id}/utiliser/  Corps : {"facture": <id>}"""
        avoir = self.get_object()
        facture = models.Facture.objects.filter(pk=request.data.get("facture")).first()
        if not facture:
            return Response({"erreur": "Facture introuvable."}, status=400)
        try:
            avoir.utiliser(facture)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(avoir).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/commercial/avoirs/{id}/pdf/ : document PDF à imprimer (?telecharger=1 pour le télécharger)."""
        from apps.core import documents
        from apps.core.pdf import telecharger
        objet = self.get_object()
        return documents.avoir(objet, request.user).reponse(f"avoir-{objet.numero}", telecharger(request))


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.COMMERCIAL, Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.CAISSIER, Profil.ADMIN_SI,))])
def impayes(request):
    """
    GET /api/commercial/impayes/
    §8.5 : factures des clients à crédit non soldées, avec échéance
    dépassée. Filtrable par ?client=<id>.
    """
    factures = models.Facture.objects.exclude(statut="ANNULEE").select_related("client")
    client_filtre = request.query_params.get("client")
    if client_filtre:
        factures = factures.filter(client_id=client_filtre)

    resultat = []
    for facture in factures:
        if facture.est_impayee:
            resultat.append({
                "facture": facture.numero,
                "client": facture.client.nom,
                "echeance": facture.date_echeance,
                "montant": facture.montant_total,
                "paye": facture.montant_paye,
                "restant": facture.solde_restant,
                "jours_retard": facture.jours_retard,
            })
    resultat.sort(key=lambda f: f["jours_retard"], reverse=True)
    return Response(resultat)



class DevisViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    """Devis : brouillon -> envoyé -> accepté (en tout ou partie, crée la commande) / refusé / expiré."""
    queryset = models.Devis.objects.select_related("client").prefetch_related("lignes__article", "commandes")
    serializer_class = serializers.DevisSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["client", "statut", "type_commande"]
    search_fields = ["numero", "client__nom"]

    def get_queryset(self):
        # Les devis envoyés dont la date de validité est passée deviennent « Expiré ».
        for devis in models.Devis.objects.filter(statut=models.StatutDevis.ENVOYE, date_validite__lt=models.Devis._aujourd_hui()):
            devis.expirer_si_depasse()
        return super().get_queryset()

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    def _action(self, methode, *args):
        devis = self.get_object()
        try:
            resultat = getattr(devis, methode)(*args)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return devis, resultat

    @action(detail=True, methods=["post"])
    def envoyer(self, request, pk=None):
        resultat = self._action("envoyer")
        return resultat if isinstance(resultat, Response) else Response(self.get_serializer(resultat[0]).data)

    @action(detail=True, methods=["post"])
    def reviser(self, request, pk=None):
        """POST .../devis/{id}/reviser/ : repasse un devis envoyé en brouillon pour le modifier."""
        resultat = self._action("reviser")
        return resultat if isinstance(resultat, Response) else Response(self.get_serializer(resultat[0]).data)

    @action(detail=True, methods=["post"])
    def refuser(self, request, pk=None):
        resultat = self._action("refuser", request.data.get("motif", ""))
        return resultat if isinstance(resultat, Response) else Response(self.get_serializer(resultat[0]).data)

    @action(detail=True, methods=["post"])
    def accepter(self, request, pk=None):
        """
        POST .../devis/{id}/accepter/  {"quantites": {"<id ligne>": quantité, ...}} (facultatif)
        Crée la commande liée (brouillon) avec les quantités acceptées.
        """
        quantites = request.data.get("quantites") or {}
        if not isinstance(quantites, dict):
            return Response({"erreur": "« quantites » : {id de ligne: quantité acceptée}."}, status=400)
        resultat = self._action("accepter", request.user, quantites)
        if isinstance(resultat, Response):
            return resultat
        devis, commande = resultat
        return Response({"devis": self.get_serializer(devis).data,
                         "commande": serializers.CommandeSerializer(commande).data}, status=201)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        """GET /api/commercial/devis/{id}/pdf/ : devis à remettre au client."""
        from apps.core import documents
        from apps.core.pdf import telecharger
        objet = self.get_object()
        return documents.devis(objet, request.user).reponse(f"devis-{objet.numero}", telecharger(request))


class LigneDevisViewSet(DerogationPrixMixin, viewsets.ModelViewSet):
    queryset = models.LigneDevis.objects.select_related("article", "devis")
    serializer_class = serializers.LigneDevisSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.COMMERCIAL, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["devis", "article"]
