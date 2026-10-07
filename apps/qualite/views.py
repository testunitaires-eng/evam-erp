"""
Vues du module qualité.

Seul le Responsable Qualité peut faire passer un lot à LIBERE.
Le Magasinier et le Commercial peuvent CONSULTER les lots (pour savoir
ce qui est vendable/sortable) mais jamais modifier leur statut.
"""

from rest_framework import viewsets
from apps.core.views import HistoriqueMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour, acces
from apps.comptes.models import Profil


LECTEURS_LOTS = (Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION,)
GESTION_LOTS = (Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI,)


class LotViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.Lot.objects.select_related("article")
    serializer_class = serializers.LotSerializer
    # Le Magasinier consulte les lots (lot d'une ligne de transfert, étiquettes),
    # mais pas le rappel (clients livrés et leurs contacts).
    permission_classes = [acces(
        lecture=LECTEURS_LOTS + (Profil.MAGASINIER,),
        ecriture=GESTION_LOTS,
    )]
    filterset_fields = ["article", "statut", "ordre_fabrication"]
    search_fields = ["numero_lot"]

    @action(detail=True, methods=["post"])
    def liberer(self, request, pk=None):
        """
        POST /api/qualite/lots/{id}/liberer/
        Réservé au Responsable Qualité. Ne fonctionne que si le lot
        est au statut Conforme.
        """
        if request.user.profil != Profil.RESPONSABLE_QUALITE and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Qualité peut libérer un lot."}, status=403)
        lot = self.get_object()
        try:
            lot.liberer(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(lot).data)

    @action(detail=True, methods=["post"])
    def bloquer(self, request, pk=None):
        """POST /api/qualite/lots/{id}/bloquer/ - réservé au Responsable Qualité."""
        if request.user.profil != Profil.RESPONSABLE_QUALITE and not request.user.is_superuser:
            return Response({"erreur": "Seul le Responsable Qualité peut bloquer un lot."}, status=403)
        lot = self.get_object()
        try:
            lot.bloquer(motif=request.data.get("motif", ""))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(lot).data)

    @action(detail=True, methods=["get"])
    def tracabilite(self, request, pk=None):
        """
        GET /api/qualite/lots/{id}/tracabilite/
        Lot de produit fini -> OF, ligne, recette, lots de matières et
        d'emballages consommés (lot fournisseur, fournisseur), contrôles,
        non-conformités, transferts vers les dépôts.
        """
        from django.db.models import Q
        from apps.production.models import ConsommationLotMatiere
        lot = self.get_object()
        of = lot.ordre_fabrication
        consommations = ConsommationLotMatiere.objects.filter(sortie__ordre_fabrication=of).select_related(
            "lot__article", "lot__fournisseur",
        ) if of else []
        controles = models.ResultatControle.objects.filter(Q(lot=lot) | Q(ordre_fabrication=of, lot__isnull=True) if of else Q(lot=lot))
        return Response({
            "lot": lot.numero_lot, "article": lot.article.code, "quantite": lot.quantite, "statut": lot.get_statut_display(),
            "date_production": lot.date_production, "date_peremption": lot.date_peremption,
            "stock": lot.lieu_stock.nom,
            "of": None if of is None else {
                "numero": of.numero, "ligne": of.ligne.code if of.ligne_id else None,
                "usine": of.usine.code if of.usine else None,
                "circuit": of.circuit.code if of.circuit_id else None,
                "recette": f"{of.fiche_technique.article.code} v{of.fiche_technique.version}" if of.fiche_technique_id else None,
                "date_debut": of.date_debut_production, "date_fin": of.date_fin,
            },
            "matieres": [
                {"lot": c.lot.numero, "article": c.lot.article.code, "lot_fournisseur": c.lot.lot_fournisseur,
                 "fournisseur": str(c.lot.fournisseur) if c.lot.fournisseur_id else None,
                 "date_peremption": c.lot.date_peremption, "quantite": c.quantite_nette}
                for c in consommations
            ],
            "controles": serializers.ResultatControleSerializer(controles.select_related("point__parametre"), many=True).data,
            "non_conformites": serializers.NonConformiteSerializer(
                models.NonConformite.objects.filter(Q(lot=lot) | Q(ordre_fabrication=of) if of else Q(lot=lot)), many=True,
            ).data,
            "transferts": [
                {"bon": m.ligne_transfert.transfert.numero, "vers": m.ligne_transfert.transfert.depot_destination.nom,
                 "quantite": -m.quantite, "statut": m.ligne_transfert.transfert.get_statut_display()}
                for m in lot.mouvements_lot.filter(ligne_transfert__isnull=False, quantite__lt=0)
                .select_related("ligne_transfert__transfert__depot_destination")
            ],
            "stock_restant": [{"lieu": depot.nom, "quantite": quantite} for depot, quantite in lot.stock_par_lieu().items()],
            "clients": clients_du_lot(lot),
            "palettes": [{"numero": p.numero, "quantite": p.quantite, "statut": p.get_statut_display(),
                          "lieu": p.depot.nom, "emplacement": p.emplacement.code if p.emplacement_id else None}
                         for p in lot.palettes.select_related("depot", "emplacement")],
        })

    @action(detail=True, methods=["get"], permission_classes=[acces(lecture=LECTEURS_LOTS, ecriture=GESTION_LOTS)])
    def rappel(self, request, pk=None):
        """
        GET /api/qualite/lots/{id}/rappel/
        Rappel de lot : clients livrés (avec contacts et quantités), stock
        restant à bloquer par lieu, palettes concernées.
        """
        lot = self.get_object()
        return Response({
            "lot": lot.numero_lot, "article": lot.article.code, "statut": lot.get_statut_display(),
            "quantite_produite": lot.quantite,
            "clients": clients_du_lot(lot),
            "stock_restant": [{"lieu": depot.nom, "quantite": quantite} for depot, quantite in lot.stock_par_lieu().items()],
            "palettes_en_stock": list(lot.palettes.filter(statut="EN_STOCK").values_list("numero", flat=True)),
        })

    @action(detail=True, methods=["post"])
    def palettiser(self, request, pk=None):
        """
        POST /api/qualite/lots/{id}/palettiser/  {"quantite_par_palette": 640} (facultatif)
        Constitue les palettes du lot libéré (packs par palette du produit par défaut).
        Réservé au Magasinier, à la Qualité et à l'Admin SI.
        """
        from apps.stocks.models import Palette
        from apps.stocks.serializers import PaletteSerializer
        if request.user.profil not in (Profil.MAGASINIER, Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI) and not request.user.is_superuser:
            return Response({"erreur": "Seuls le Magasinier et la Qualité constituent les palettes."}, status=403)
        lot = self.get_object()
        try:
            palettes = Palette.constituer(lot, request.user, request.data.get("quantite_par_palette") or None)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(PaletteSerializer(palettes, many=True).data, status=201)

    @action(detail=True, methods=["get"])
    def etiquettes_palettes(self, request, pk=None):
        """GET /api/qualite/lots/{id}/etiquettes_palettes/ : toutes les étiquettes du lot (PDF)."""
        from django.http import HttpResponse
        from apps.core.documents import etiquette_palettes
        lot = self.get_object()
        palettes = list(lot.palettes.select_related("lot__article", "depot", "emplacement"))
        if not palettes:
            return Response({"erreur": "Ce lot n'est pas encore palettisé."}, status=400)
        reponse = HttpResponse(etiquette_palettes(palettes, request.user), content_type="application/pdf")
        reponse["Content-Disposition"] = f'inline; filename="palettes-{lot.numero_lot}.pdf"'
        return reponse


class ControleQualiteViewSet(viewsets.ModelViewSet):
    queryset = models.ControleQualite.objects.all()
    serializer_class = serializers.ControleQualiteSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION,),
        ecriture=(Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["lot", "resultat"]

    def perform_create(self, serializer):
        serializer.save(controleur=self.request.user)


# ---------------------------------------------------------------------
# Module Contrôle qualité
# ---------------------------------------------------------------------
import django_filters
from django.db.models import Count, Q
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser

LECTEURS_QUALITE = (Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.MAGASINIER, Profil.COMPTABILITE_DAF,)
PARAMETRAGE_QUALITE = acces(lecture=LECTEURS_QUALITE, ecriture=(Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI,))


def _est_qualite(utilisateur):
    return utilisateur.is_superuser or utilisateur.profil in (Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI)




class ParametreQualiteViewSet(viewsets.ModelViewSet):
    queryset = models.ParametreQualite.objects.all()
    serializer_class = serializers.ParametreQualiteSerializer
    permission_classes = [PARAMETRAGE_QUALITE]
    filterset_fields = ["famille", "type_resultat", "actif"]
    search_fields = ["libelle", "code"]


class InstrumentViewSet(viewsets.ModelViewSet):
    queryset = models.Instrument.objects.all()
    serializer_class = serializers.InstrumentSerializer
    permission_classes = [PARAMETRAGE_QUALITE]
    filterset_fields = ["laboratoire", "actif"]
    search_fields = ["code", "designation", "numero_serie"]

    @action(detail=False, methods=["get"])
    def a_etalonner(self, request):
        """GET .../instruments/a_etalonner/ : instruments dont l'étalonnage est dépassé ou jamais fait."""
        instruments = [i for i in self.get_queryset().filter(actif=True) if not i.etalonnage_valide]
        return Response(self.get_serializer(instruments, many=True).data)


class ModeleControleViewSet(viewsets.ModelViewSet):
    """Bibliothèque de contrôles réutilisables (paramètre, instrument, méthode, échantillon...)."""
    queryset = models.ModeleControle.objects.select_related("parametre", "instrument")
    serializer_class = serializers.ModeleControleSerializer
    permission_classes = [PARAMETRAGE_QUALITE]
    filterset_fields = ["parametre", "instrument", "laboratoire", "actif"]
    search_fields = ["code", "designation"]


class PointControleViewSet(viewsets.ModelViewSet):
    """Plan de contrôle : ce qui doit être contrôlé, où, quand, comment et avec quels critères."""
    queryset = models.PointControle.objects.select_related("parametre", "activite", "article", "etape")
    serializer_class = serializers.PointControleSerializer
    permission_classes = [PARAMETRAGE_QUALITE]
    filterset_fields = ["activite", "article", "fiche_technique", "etape", "poste", "equipement", "parametre",
                        "declencheur", "bloquant", "statut", "laboratoire"]
    search_fields = ["code", "designation"]

    def _statut(self, request, statut):
        point = self.get_object()
        point.statut = statut
        point.save()
        return Response(self.get_serializer(point).data)

    @action(detail=True, methods=["post"])
    def activer(self, request, pk=None):
        """POST .../plan-controle/{id}/activer/ (exige les critères d'acceptation d'un contrôle mesuré)."""
        return self._statut(request, models.StatutPointControle.ACTIF)

    @action(detail=True, methods=["post"])
    def desactiver(self, request, pk=None):
        return self._statut(request, models.StatutPointControle.INACTIF)

    @action(detail=True, methods=["post"])
    def nouvelle_version(self, request, pk=None):
        """POST .../plan-controle/{id}/nouvelle_version/ : copie modifiable ; l'ancienne version est désactivée."""
        return Response(self.get_serializer(self.get_object().nouvelle_version()).data, status=201)


class ResultatControleFiltre(django_filters.FilterSet):
    du = django_filters.IsoDateTimeFilter(field_name="date_prevue", lookup_expr="gte")
    au = django_filters.IsoDateTimeFilter(field_name="date_prevue", lookup_expr="lte")
    activite = django_filters.NumberFilter(method="filtrer_activite")
    parametre = django_filters.NumberFilter(field_name="point__parametre")
    famille = django_filters.CharFilter(field_name="point__parametre__famille")
    bloquant = django_filters.BooleanFilter(field_name="point__bloquant")
    recette = django_filters.NumberFilter(field_name="ordre_fabrication__fiche_technique")
    fournisseur = django_filters.NumberFilter(field_name="lot_matiere__fournisseur")
    action_corrective = django_filters.BooleanFilter(method="filtrer_action_corrective")
    en_retard = django_filters.BooleanFilter(method="filtrer_en_retard")

    class Meta:
        model = models.ResultatControle
        fields = [
            "statut", "point", "ordre_fabrication", "lot", "lot_matiere", "article", "ligne", "etape", "poste",
            "equipement", "operateur", "valide_par", "instrument", "est_reprise", "conforme",
        ]

    def filtrer_activite(self, queryset, nom, valeur):
        return queryset.filter(Q(point__activite_id=valeur) | Q(article__activite_id=valeur))

    def filtrer_action_corrective(self, queryset, nom, valeur):
        avec = queryset.filter(non_conformites__action_corrective__gt="").distinct()
        return avec if valeur else queryset.exclude(pk__in=avec.values("pk"))

    def filtrer_en_retard(self, queryset, nom, valeur):
        from django.utils import timezone
        retard = Q(statut__in=models.STATUTS_EN_ATTENTE, date_prevue__lt=timezone.now())
        return queryset.filter(retard) if valeur else queryset.exclude(retard)


class ResultatControleViewSet(viewsets.ModelViewSet):
    """
    Contrôles à réaliser (générés selon le plan) et réalisés.
    L'Agent Production saisit les contrôles de SES OF en production ; la
    Qualité saisit tout, valide, annule et ouvre les reprises.
    """
    queryset = models.ResultatControle.objects.select_related(
        "point__parametre", "ordre_fabrication", "lot", "lot_matiere", "operateur",
    )
    serializer_class = serializers.ResultatControleSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_QUALITE, Profil.RESPONSABLE_PRODUCTION, Profil.AGENT_PRODUCTION, Profil.MAGASINIER, Profil.ADMIN_SI,),
    )]
    filterset_class = ResultatControleFiltre
    search_fields = ["numero", "point__designation", "reference_echantillon"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        queryset = super().get_queryset()
        utilisateur = self.request.user
        if not utilisateur.is_superuser and utilisateur.profil == Profil.AGENT_PRODUCTION:
            return queryset.filter(ordre_fabrication__agents_affectes=utilisateur)
        if not utilisateur.is_superuser and utilisateur.profil == Profil.MAGASINIER:
            return queryset.filter(lot_matiere__isnull=False)
        return queryset

    def perform_create(self, serializer):
        """Contrôle ponctuel ajouté à la main (Qualité / Responsable Production)."""
        if self.request.user.profil not in (Profil.RESPONSABLE_QUALITE, Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI) \
                and not self.request.user.is_superuser:
            raise PermissionDenied("Les contrôles sont générés par le plan ; seule la Qualité ou la Production en ajoute.")
        from django.utils import timezone
        serializer.save(date_prevue=serializer.validated_data.get("date_prevue") or timezone.now())

    def _verifier_saisie(self, resultat):
        utilisateur = self.request.user
        if _est_qualite(utilisateur) or utilisateur.profil == Profil.RESPONSABLE_PRODUCTION:
            return
        if utilisateur.profil == Profil.AGENT_PRODUCTION:
            of = resultat.ordre_fabrication
            if of is None or not of.agents_affectes.filter(pk=utilisateur.pk).exists():
                raise PermissionDenied("Vous n'êtes pas affecté à l'OF de ce contrôle.")
            if of.statut not in ("EN_PRODUCTION", "PRODUCTION_TERMINEE", "EN_CONTROLE"):
                raise PermissionDenied(f"L'OF {of.numero} n'est pas en production.")
            return
        if utilisateur.profil == Profil.MAGASINIER and resultat.lot_matiere_id:
            return
        raise PermissionDenied("Votre profil ne saisit pas ce contrôle.")

    @action(detail=False, methods=["get"])
    def export(self, request):
        """
        GET .../controles-realises/export/?type=xlsx|pdf + les filtres de la liste
        (période, activité, OF, lot, ligne, étape, statut, bloquant...).
        """
        from decimal import Decimal
        from apps.core.exports import classeur, tableau_pdf
        from apps.core.pdf import date_fr, nombre, telecharger
        resultats = self.filter_queryset(self.get_queryset()).select_related(
            "point__parametre", "ordre_fabrication", "lot", "lot_matiere", "article", "ligne", "etape", "equipement",
            "operateur", "instrument",
        )[:5000]
        entetes = ["N°", "Prévu le", "Réalisé le", "Contrôle", "Paramètre", "Valeur", "Unité", "Critère", "Statut",
                   "Bloquant", "OF", "Lot", "Article", "Ligne", "Étape", "Machine", "Opérateur", "Instrument", "Reprise", "Commentaire"]
        serializer = serializers.ResultatControleSerializer()
        lignes = [[
            r.numero, r.date_prevue, r.date_realisation, r.point.designation, r.point.parametre.libelle,
            r.valeur if r.valeur is not None else (r.resultat_qualitatif or None), r.point.parametre.unite,
            serializer.get_critere(r), r.get_statut_display(), "Oui" if r.point.bloquant else "Non",
            r.ordre_fabrication.numero if r.ordre_fabrication_id else (r.lot_matiere.numero if r.lot_matiere_id else None),
            r.lot.numero_lot if r.lot_id else None, r.article.code if r.article_id else None,
            r.ligne.code if r.ligne_id else None, r.etape.libelle if r.etape_id else None,
            r.equipement.code if r.equipement_id else None,
            (r.operateur.get_full_name() or r.operateur.username) if r.operateur_id else None,
            r.instrument.code if r.instrument_id else None, "Oui" if r.est_reprise else "Non", r.commentaire,
        ] for r in resultats]
        if request.query_params.get("type") == "pdf":
            courtes = [[l[0], date_fr(l[2] or l[1]), l[3], nombre(l[5]) if isinstance(l[5], Decimal) else (l[5] or ""),
                        l[7] or "", l[8], l[10] or "", l[12] or ""] for l in lignes]
            document = tableau_pdf(
                "CONTRÔLES QUALITÉ", timezone_maintenant_texte(), ["N°", "Date", "Contrôle", "Valeur", "Critère", "Statut", "OF / lot", "Article"],
                courtes, [22, 24, None, 18, 30, 22, 22, 20], request.user, colonnes_nombres=(3,),
                texte_avant=f"{len(courtes)} contrôle(s) selon les filtres appliqués.",
            )
            return document.reponse("controles-qualite", telecharger(request))
        return classeur([("Contrôles qualité", entetes, lignes)], "controles-qualite")

    @action(detail=True, methods=["post"])
    def enregistrer(self, request, pk=None):
        """
        POST .../controles-realises/{id}/enregistrer/
        Corps : {"valeur": 3.6} (contrôle mesuré) ou {"resultat_qualitatif": "CONFORME"},
        + "instrument", "commentaire", "reference_echantillon" facultatifs.
        Conformité calculée selon le plan ; non conforme -> NC automatique
        (bloquante si le contrôle l'est).
        """
        resultat = self.get_object()
        self._verifier_saisie(resultat)
        instrument = None
        if request.data.get("instrument"):
            instrument = models.Instrument.objects.filter(pk=request.data["instrument"], actif=True).first()
            if instrument is None:
                return Response({"erreur": "Instrument introuvable ou inactif."}, status=400)
        try:
            resultat.enregistrer(
                operateur=request.user, valeur=request.data.get("valeur"),
                resultat_qualitatif=request.data.get("resultat_qualitatif", ""), instrument=instrument,
                commentaire=request.data.get("commentaire", ""),
                reference_echantillon=request.data.get("reference_echantillon", ""),
                valide_par=request.user if _est_qualite(request.user) else None,
            )
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(resultat).data)

    @action(detail=True, methods=["post"])
    def envoyer_au_laboratoire(self, request, pk=None):
        """POST .../{id}/envoyer_au_laboratoire/ {"reference_echantillon": "..."} : en attente du résultat."""
        resultat = self.get_object()
        self._verifier_saisie(resultat)
        try:
            resultat.soumettre_au_laboratoire(request.user, request.data.get("reference_echantillon", ""))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(resultat).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        """POST .../{id}/annuler/ {"motif": "..."} (Qualité uniquement)."""
        if not _est_qualite(request.user):
            return Response({"erreur": "Seul le Responsable Qualité annule un contrôle."}, status=403)
        resultat = self.get_object()
        try:
            resultat.annuler(request.data.get("motif", ""))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(resultat).data)

    @action(detail=True, methods=["post"])
    def reprise(self, request, pk=None):
        """POST .../{id}/reprise/ : ouvre un contrôle de reprise (nouveau contrôle / contre-analyse)."""
        if not (_est_qualite(request.user) or request.user.profil == Profil.RESPONSABLE_PRODUCTION):
            return Response({"erreur": "Seule la Qualité ou la Production ouvre une reprise."}, status=403)
        try:
            reprise = self.get_object().creer_reprise()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(reprise).data, status=201)


class NonConformiteViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    queryset = models.NonConformite.objects.select_related("resultat", "ordre_fabrication", "lot", "lot_matiere")
    serializer_class = serializers.NonConformiteSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER, Profil.RESPONSABLE_ACHATS,),
        ecriture=(Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["statut", "bloquante", "ordre_fabrication", "lot", "lot_matiere", "responsable", "decision", "action_immediate"]
    search_fields = ["numero", "description"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(ouverte_par=self.request.user)

    @action(detail=True, methods=["post"])
    def prendre_en_charge(self, request, pk=None):
        """POST .../{id}/prendre_en_charge/ : Ouverte -> Action en cours."""
        nc = self.get_object()
        nc.statut = models.StatutNC.EN_COURS
        nc.save()
        return Response(self.get_serializer(nc).data)

    @action(detail=True, methods=["post"])
    def cloturer(self, request, pk=None):
        """POST .../{id}/cloturer/ {"decision": "LIBERATION|REPRISE|REJET|QUARANTAINE", "action_corrective": "..."}"""
        nc = self.get_object()
        try:
            nc.cloturer(request.user, request.data.get("decision", ""), request.data.get("action_corrective", ""))
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(nc).data)


class PieceJointeQualiteViewSet(viewsets.ModelViewSet):
    """Photos et documents (multipart : champ « fichier ») joints à un contrôle ou une NC."""
    queryset = models.PieceJointeQualite.objects.defer("contenu")
    serializer_class = serializers.PieceJointeQualiteSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION,),
        ecriture=(Profil.RESPONSABLE_QUALITE, Profil.AGENT_PRODUCTION, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["resultat", "non_conformite"]
    http_method_names = ["get", "post", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(ajoute_par=self.request.user)

    @action(detail=True, methods=["get"])
    def fichier(self, request, pk=None):
        """GET .../pieces-jointes/{id}/fichier/ : le fichier lui-même (mêmes droits que la pièce jointe)."""
        from django.http import HttpResponse
        piece = self.get_object()
        reponse = HttpResponse(bytes(piece.contenu), content_type=piece.type_contenu)
        reponse["Content-Disposition"] = f'inline; filename="{piece.nom_fichier}"'
        return reponse


@api_view(["GET"])
@drf_permission_classes([acces(lecture=(Profil.RESPONSABLE_QUALITE, Profil.DIRECTION, Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI))])
def indicateurs_qualite(request):
    """
    GET /api/qualite/indicateurs/?du=AAAA-MM-JJ&au=AAAA-MM-JJ&activite=<id>
    Taux de conformité, NC par produit / étape / ligne / machine,
    contrôles manquants (en retard), NC ouvertes, instruments à étalonner.
    """
    from django.utils import timezone
    realises = models.ResultatControle.objects.filter(statut__in=(models.StatutResultat.CONFORME, models.StatutResultat.NON_CONFORME))
    nc = models.NonConformite.objects.all()
    if request.query_params.get("du"):
        realises = realises.filter(date_realisation__date__gte=request.query_params["du"])
        nc = nc.filter(date_ouverture__date__gte=request.query_params["du"])
    if request.query_params.get("au"):
        realises = realises.filter(date_realisation__date__lte=request.query_params["au"])
        nc = nc.filter(date_ouverture__date__lte=request.query_params["au"])
    if request.query_params.get("activite"):
        realises = realises.filter(Q(point__activite_id=request.query_params["activite"]) | Q(article__activite_id=request.query_params["activite"]))
        nc = nc.filter(resultat__in=realises)
    total = realises.count()
    conformes = realises.filter(statut=models.StatutResultat.CONFORME).count()

    def repartition(champ, libelle):
        lignes = realises.values(libelle).annotate(
            controles=Count("id"), non_conformes=Count("id", filter=Q(statut=models.StatutResultat.NON_CONFORME)),
        ).order_by("-non_conformes")
        return [
            {"cle": ligne[libelle] or "-", "controles": ligne["controles"], "non_conformes": ligne["non_conformes"],
             "taux_conformite": round(100 * (ligne["controles"] - ligne["non_conformes"]) / ligne["controles"], 2)}
            for ligne in lignes
        ]

    en_retard = models.ResultatControle.objects.filter(statut__in=models.STATUTS_EN_ATTENTE, date_prevue__lt=timezone.now())
    donnees = {
        "controles_realises": total,
        "conformes": conformes,
        "taux_conformite": round(100 * conformes / total, 2) if total else None,
        "par_produit": repartition("article", "article__code"),
        "par_etape": repartition("etape", "etape__libelle"),
        "par_ligne": repartition("ligne", "ligne__code"),
        "par_machine": repartition("equipement", "equipement__code"),
        "par_parametre": repartition("parametre", "point__parametre__libelle"),
        "non_conformites": {
            "total": nc.count(),
            "ouvertes": nc.exclude(statut=models.StatutNC.CLOTUREE).count(),
            "bloquantes_ouvertes": nc.filter(bloquante=True).exclude(statut=models.StatutNC.CLOTUREE).count(),
            "par_decision": dict(nc.exclude(decision="").values_list("decision").annotate(n=Count("id"))),
        },
        "controles_en_retard": en_retard.count(),
        "controles_en_retard_bloquants": en_retard.filter(point__bloquant=True).count(),
        "instruments_a_etalonner": [i.code for i in models.Instrument.objects.filter(actif=True) if not i.etalonnage_valide],
    }
    if request.query_params.get("type") in ("xlsx", "pdf"):
        return _exporter_indicateurs(request, donnees)
    return Response(donnees)


def timezone_maintenant_texte():
    from django.utils import timezone
    return timezone.localtime().strftime("%Y-%m-%d")


def _exporter_indicateurs(request, donnees):
    """?type=xlsx (une feuille par axe) ou ?type=pdf (synthèse imprimable)."""
    from apps.core.exports import classeur
    from apps.core.pdf import DocumentPDF, nombre, telecharger
    from django.utils import timezone
    axes = [("Par produit", "par_produit"), ("Par étape", "par_etape"), ("Par ligne", "par_ligne"),
            ("Par machine", "par_machine"), ("Par paramètre", "par_parametre")]
    entetes = ["", "Contrôles", "Non conformes", "Taux de conformité (%)"]
    synthese = [
        ["Contrôles réalisés", donnees["controles_realises"]], ["Conformes", donnees["conformes"]],
        ["Taux de conformité (%)", donnees["taux_conformite"]],
        ["Non-conformités", donnees["non_conformites"]["total"]], ["NC ouvertes", donnees["non_conformites"]["ouvertes"]],
        ["NC bloquantes ouvertes", donnees["non_conformites"]["bloquantes_ouvertes"]],
        ["Contrôles en retard", donnees["controles_en_retard"]],
        ["dont bloquants", donnees["controles_en_retard_bloquants"]],
        ["Instruments à étalonner", ", ".join(donnees["instruments_a_etalonner"]) or "aucun"],
    ]
    periode = " - ".join(x for x in (request.query_params.get("du"), request.query_params.get("au")) if x) or "toutes dates"
    if request.query_params.get("type") == "xlsx":
        feuilles = [("Synthèse", ["Indicateur", "Valeur"], synthese)]
        feuilles += [(titre, ["Axe"] + entetes[1:], [[l["cle"], l["controles"], l["non_conformes"], l["taux_conformite"]] for l in donnees[cle]])
                     for titre, cle in axes]
        return classeur(feuilles, "indicateurs-qualite")
    document = DocumentPDF("INDICATEURS QUALITÉ", periode, timezone.now(), request.user)
    document.avec_lignes(["Indicateur", "Valeur"], [[l[0], nombre(l[1]) if isinstance(l[1], (int, float)) else (l[1] if l[1] is not None else "-")] for l in synthese],
                         [None, 50], colonnes_nombres=(1,))
    for titre, cle in axes:
        if donnees[cle]:
            document.avec_texte(f"<b>{titre}</b>")
            document.avec_lignes(["Axe"] + entetes[1:], [[l["cle"], l["controles"], l["non_conformes"], nombre(l["taux_conformite"])] for l in donnees[cle]],
                                 [None, 28, 32, 42], colonnes_nombres=(1, 2, 3))
    return document.reponse("indicateurs-qualite", telecharger(request))



def clients_du_lot(lot):
    """Traçabilité aval : chaque client livré de ce lot (commande, BL, quantité, contact)."""
    clients = {}
    for mouvement in lot.mouvements_lot.filter(ligne_commande__isnull=False).select_related(
        "ligne_commande__commande__client",
    ):
        commande = mouvement.ligne_commande.commande
        client = commande.client
        bon = getattr(commande, "bon_livraison", None)
        ligne = clients.setdefault(client.pk, {
            "client": client.nom, "code": client.code, "telephone": client.telephone, "adresse": client.adresse,
            "quantite": 0, "livraisons": [],
        })
        ligne["quantite"] += -mouvement.quantite
        ligne["livraisons"].append({
            "commande": commande.numero, "bon_livraison": bon.numero if bon else None,
            "date": mouvement.date, "quantite": -mouvement.quantite,
        })
    return list(clients.values())
