"""Vues du module comptabilité/pilotage - accès transversal en lecture
pour Comptabilité/DAF et Direction, écriture réservée à Comptabilité/
DAF et Administrateur SI."""

import csv

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour, acces
from apps.comptes.models import Profil


class AnomalieDetecteeViewSet(viewsets.ModelViewSet):
    queryset = models.AnomalieDetectee.objects.all()
    serializer_class = serializers.AnomalieDetecteeSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["type_anomalie", "module_source", "statut"]
    # Détectées par le système : ni création, ni modification, ni suppression
    # à la main ; elles se traitent par les actions ci-dessous.
    http_method_names = ["get", "post", "head", "options"]

    def create(self, request, *args, **kwargs):
        return Response({"erreur": "Les anomalies sont détectées automatiquement : utilisez /detecter/ pour lancer les contrôles."}, status=400)

    def _changer_statut(self, request, statut, commentaire_obligatoire=False):
        anomalie = self.get_object()
        if anomalie.statut in (models.StatutAnomalie.TRAITEE, models.StatutAnomalie.IGNOREE):
            return Response({"erreur": f"Cette anomalie est déjà « {anomalie.get_statut_display()} »."}, status=400)
        commentaire = (request.data.get("commentaire") or "").strip()
        if commentaire_obligatoire and not commentaire:
            return Response({"erreur": "Le commentaire est obligatoire."}, status=400)
        anomalie.statut = statut
        anomalie.traite_par = request.user
        anomalie.commentaire_traitement = commentaire or anomalie.commentaire_traitement
        if statut != models.StatutAnomalie.EN_TRAITEMENT:
            anomalie.date_traitement = timezone.now()
        anomalie.save()
        return Response(self.get_serializer(anomalie).data)

    @action(detail=True, methods=["post"])
    def prendre_en_charge(self, request, pk=None):
        """POST .../prendre_en_charge/ - passe l'anomalie « En traitement »."""
        return self._changer_statut(request, models.StatutAnomalie.EN_TRAITEMENT)

    @action(detail=True, methods=["post"])
    def resoudre(self, request, pk=None):
        """POST .../resoudre/  Corps : {"commentaire": "..."} (obligatoire)."""
        return self._changer_statut(request, models.StatutAnomalie.TRAITEE, commentaire_obligatoire=True)

    @action(detail=True, methods=["post"])
    def ignorer(self, request, pk=None):
        """POST .../ignorer/  Corps : {"commentaire": "justification"} (obligatoire)."""
        return self._changer_statut(request, models.StatutAnomalie.IGNOREE, commentaire_obligatoire=True)

    @action(detail=False, methods=["post"])
    def detecter(self, request):
        """POST .../detecter/ - lance immédiatement les contrôles périodiques."""
        from .anomalies import detecter_anomalies
        creees, resolues = detecter_anomalies()
        return Response({"detectees": creees, "resolues_automatiquement": resolues})


class ExportComptableViewSet(viewsets.ModelViewSet):
    queryset = models.ExportComptable.objects.all()
    serializer_class = serializers.ExportComptableSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["type_export"]

    JOURNAUX_PAR_EXPORT = {
        models.TypeExport.VENTES: [models.Journal.VENTES],
        models.TypeExport.ENCAISSEMENTS: [models.Journal.CAISSE],
        models.TypeExport.ACHATS: [models.Journal.ACHATS],
        models.TypeExport.JOURNAL: [choix for choix, _ in models.Journal.choices],
    }

    def perform_create(self, serializer):
        serializer.save(genere_par=self.request.user)

    @action(detail=True, methods=["get"])
    def telecharger(self, request, pk=None):
        """
        GET /api/comptabilite/exports/{id}/telecharger/
        Fichier CSV d'import Sage 100 (séparateur « ; », décimales à la
        virgule, dates JJ/MM/AAAA) : une ligne par ligne d'écriture de la
        période et des journaux de l'export. Les écritures sont marquées
        « exportées » (date) pour le rapprochement.
        """
        export = self.get_object()
        ecritures = models.EcritureComptable.objects.filter(
            date__gte=export.periode_debut, date__lte=export.periode_fin,
            journal__in=self.JOURNAUX_PAR_EXPORT[export.type_export],
        ).prefetch_related("lignes")
        reponse = HttpResponse(content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = (
            f'attachment; filename="export_{export.type_export.lower()}_{export.periode_debut}_{export.periode_fin}.csv"'
        )
        ecrivain = csv.writer(reponse, delimiter=";")
        ecrivain.writerow(["Journal", "Date", "Piece", "Compte general", "Compte tiers", "Libelle", "Debit", "Credit"])
        for ecriture in ecritures:
            for ligne in ecriture.lignes.all():
                ecrivain.writerow([
                    ecriture.journal, ecriture.date.strftime("%d/%m/%Y"), ecriture.piece, ligne.compte,
                    ligne.compte_tiers, ligne.libelle,
                    f"{ligne.debit:.2f}".replace(".", ","), f"{ligne.credit:.2f}".replace(".", ","),
                ])
        ecritures.filter(exportee_le__isnull=True).update(exportee_le=timezone.now())
        return reponse


class CompteParametreViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Plan de comptes utilisé par les écritures automatiques : un numéro par
    rôle (clients, ventes, TVA, caisse...). Valeurs SYSCOHADA proposées
    par défaut, modifiables par la Comptabilité/DAF (le rôle ne change pas).
    """
    queryset = models.CompteParametre.objects.all()
    serializer_class = serializers.CompteParametreSerializer
    permission_classes = [acces(lecture=(Profil.DIRECTION,), ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI))]


class ParametreControleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """
    Seuils des contrôles automatiques d'anomalies (tolérance de
    dépassement matière, alerte péremption, délai d'autorisation des
    décaissements). Réglés par la Comptabilité/DAF ; bornes vérifiées ;
    chaque modification est tracée (qui, quand).
    """
    queryset = models.ParametreControle.objects.all()
    serializer_class = serializers.ParametreControleSerializer
    permission_classes = [acces(lecture=(Profil.DIRECTION,), ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI))]

    def perform_update(self, serializer):
        # Ancienne -> nouvelle valeur, auteur et date : journal automatique.
        serializer.save(modifie_par=self.request.user)


class EcritureComptableViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Écritures générées automatiquement par les documents (lecture seule :
    une erreur se corrige en annulant le document, qui contre-passe).
    Filtres : ?journal=VT&date_debut=AAAA-MM-JJ&date_fin=AAAA-MM-JJ&piece=FACT-000001
    """
    serializer_class = serializers.EcritureComptableSerializer
    permission_classes = [acces(lecture=(Profil.COMPTABILITE_DAF, Profil.DIRECTION, Profil.ADMIN_SI))]
    filterset_fields = ["journal", "piece"]
    search_fields = ["piece", "libelle", "numero"]

    def get_queryset(self):
        queryset = models.EcritureComptable.objects.prefetch_related("lignes")
        parametres = self.request.query_params
        if parametres.get("date_debut"):
            queryset = queryset.filter(date__gte=parametres["date_debut"])
        if parametres.get("date_fin"):
            queryset = queryset.filter(date__lte=parametres["date_fin"])
        return queryset


class ClotureViewSet(viewsets.ModelViewSet):
    queryset = models.Cloture.objects.all()
    serializer_class = serializers.ClotureSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION,),
        ecriture=(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["type_cloture", "periode"]

    def perform_create(self, serializer):
        serializer.save(valide_par=self.request.user)
