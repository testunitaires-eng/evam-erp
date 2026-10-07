"""
Vues du module référentiel.

Règle clé du cahier des charges : le Magasinier NE PEUT PAS créer ou
modifier une fiche technique. Seuls Responsable Production et
Administrateur SI le peuvent ; les autres profils sont en lecture
seule sur ce module.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from apps.core.views import HistoriqueMixin
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour, acces
from apps.comptes.models import Profil


# class ArticleViewSet(viewsets.ModelViewSet):
#     queryset = models.Article.objects.all()
#     serializer_class = serializers.ArticleSerializer
#     permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
#     filterset_fields = ["type_article", "famille", "actif"]
#     search_fields = ["code", "designation"]

class ArticleViewSet(viewsets.ModelViewSet):
    queryset = models.Article.objects.all()
    serializer_class = serializers.ArticleSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.MAGASINIER, Profil.COMMERCIAL, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["type_article", "famille", "actif"]
    search_fields = ["code", "designation"]

    def perform_create(self, serializer):
        """Un produit fini reçoit automatiquement sa fiche de composition (brouillon)."""
        article = serializer.save()
        article.creer_fiche_technique_brouillon(self.request.user)

    def perform_update(self, serializer):
        """Idem si un article devient produit fini après coup."""
        article = serializer.save()
        article.creer_fiche_technique_brouillon(self.request.user)

# class FicheTechniqueViewSet(viewsets.ModelViewSet):
#     queryset = models.FicheTechnique.objects.all()
#     serializer_class = serializers.FicheTechniqueSerializer
#     permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
#     filterset_fields = ["article", "statut"]

#     @action(detail=True, methods=["post"])
#     def valider(self, request, pk=None):
#         """
#         POST /api/referentiel/fiches-techniques/{id}/valider/
#         Fait passer la fiche de BROUILLON à VALIDEE.
#         """
#         fiche = self.get_object()
#         try:
#             fiche.valider(request.user)
#         except ValueError as erreur:
#             return Response({"erreur": str(erreur)}, status=400)
#         return Response(self.get_serializer(fiche).data)



# class FicheTechniqueViewSet(viewsets.ModelViewSet):
#     queryset = models.FicheTechnique.objects.all()
#     serializer_class = serializers.FicheTechniqueSerializer
#     permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
#     filterset_fields = ["article", "statut"]


class FicheTechniqueViewSet(HistoriqueMixin, viewsets.ModelViewSet):
    """
    Paramétrage des fiches de composition : réservé à l'ADMIN_SI
    (création de version, validation, archivage). Lecture pour tous
    (le Responsable Production et le Magasinier la consultent).
    """
    queryset = models.FicheTechnique.objects.all()
    serializer_class = serializers.FicheTechniqueSerializer
    # La Qualité lit les recettes pour son plan de contrôle (sans les prix).
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.ADMIN_SI,),
    )]
    filterset_fields = ["article", "statut"]
    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """
        POST /api/referentiel/fiches-techniques/{id}/valider/
        Fait passer la fiche de BROUILLON à VALIDEE.
        """
        fiche = self.get_object()
        try:
            fiche.valider(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(fiche).data)

    @action(detail=True, methods=["get"])
    def elements_disponibles(self, request, pk=None):
        """
        GET /api/referentiel/fiches-techniques/{id}/elements_disponibles/
        Liste de choix de la composition, lue en base : matières
        premières et produits intermédiaires actifs, pas encore présents
        dans la fiche. Filtre optionnel : ?type_article=MATIERE_PREMIERE
        """
        elements = self.get_object().elements_disponibles()
        type_article = request.query_params.get("type_article")
        if type_article:
            elements = elements.filter(type_article=type_article)
        return Response(serializers.ElementCompositionSerializer(elements, many=True).data)

    @action(detail=True, methods=["post"])
    def ajouter_elements(self, request, pk=None):
        """
        POST /api/referentiel/fiches-techniques/{id}/ajouter_elements/
        Corps : {"elements": [{"matiere": <id>, "quantite_necessaire": "0.5", "prix_unitaire": "1000"}, ...]}
        Ajoute en une fois les éléments choisis dans la liste
        elements_disponibles (tout ou rien). Réservé à l'ADMIN_SI.
        """
        fiche = self.get_object()
        fiche.ajouter_elements(request.data.get("elements"))
        fiche.refresh_from_db()
        return Response(self.get_serializer(fiche).data, status=201)

    @action(detail=True, methods=["post"])
    def mettre_a_jour_prix(self, request, pk=None):
        """
        POST .../fiches-techniques/{id}/mettre_a_jour_prix/ {"prix": {"<id matière>": "1100", ...}}
        Nouvelle version validée avec les nouveaux prix ; l'ancienne est archivée (historique conservé).
        """
        fiche = self.get_object()
        try:
            copie = fiche.mettre_a_jour_prix(request.data.get("prix"), request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(copie).data, status=201)

    @action(detail=True, methods=["post"])
    def mettre_en_test(self, request, pk=None):
        """POST .../fiches-techniques/{id}/mettre_en_test/ : Brouillon -> En test (composition figée pendant l'essai)."""
        fiche = self.get_object()
        try:
            fiche.mettre_en_test()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(fiche).data)

    @action(detail=True, methods=["post"])
    def repasser_en_brouillon(self, request, pk=None):
        """POST .../fiches-techniques/{id}/repasser_en_brouillon/ : En test -> Brouillon (ajustement après essai)."""
        fiche = self.get_object()
        try:
            fiche.repasser_en_brouillon()
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(fiche).data)

    # Simulation chiffrée : pas pour la Qualité.
    @action(detail=True, methods=["get"], permission_classes=[acces(lecture=(Profil.RESPONSABLE_PRODUCTION,), ecriture=(Profil.ADMIN_SI,))])
    def simuler_besoins(self, request, pk=None):
        """
        GET .../fiches-techniques/{id}/simuler_besoins/?article=<id>&quantite=<q>
        Besoins que générerait un OF (unité de référence, rendement, pertes,
        lignes propres au format) : contrôle de la recette avant validation.
        """
        from apps.core.validation import convertir_decimal
        fiche = self.get_object()
        article = models.Article.objects.filter(pk=request.query_params.get("article") or fiche.article_id).first()
        try:
            quantite = convertir_decimal(request.query_params.get("quantite"), "La quantité")
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        besoins = fiche.besoins_pour(article, quantite)
        return Response({
            "article": article.code, "quantite": quantite,
            "besoins": [
                {
                    "matiere": ligne.matiere.code, "designation": ligne.matiere.designation,
                    "unite": ligne.matiere.unite_mesure, "base_calcul": ligne.base_calcul,
                    "quantite": besoin.quantize(models.Decimal("0.0001")),
                    "montant": (besoin * ligne.prix_unitaire).quantize(models.Decimal("0.01")),
                }
                for ligne, besoin in besoins
            ],
        })


class CompositionFicheTechniqueViewSet(viewsets.ModelViewSet):
    """Lignes de composition (matières et quantités par unité produite) : écriture ADMIN_SI uniquement."""
    queryset = models.CompositionFicheTechnique.objects.all()
    serializer_class = serializers.CompositionFicheTechniqueSerializer
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.ADMIN_SI,),
    )]
    filterset_fields = ["fiche_technique", "matiere"]


class FicheConditionnementViewSet(viewsets.ModelViewSet):
    queryset = models.FicheConditionnement.objects.all()
    serializer_class = serializers.FicheConditionnementSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
    filterset_fields = ["article"]




@extend_schema(deprecated=True, description="Obsolète : remplacé par le plan de contrôle (/api/qualite/plan-controle/).")
class ControleQualiteRequisViewSet(viewsets.ModelViewSet):
    """
    Ancienne liste des contrôles attendus (bloc 7 de la fiche article),
    remplacée par le plan de contrôle du module qualité et utilisée par
    aucun calcul : consultable, plus modifiable (Admin SI pour le ménage).
    """
    queryset = models.ControleQualiteRequis.objects.all()
    serializer_class = serializers.ControleQualiteRequisSerializer
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_QUALITE,),
        ecriture=(Profil.ADMIN_SI,),
    )]
    filterset_fields = ["article", "moment", "obligatoire"]






class FamilleArticleViewSet(viewsets.ModelViewSet):
    """Liste déroulante des familles - écriture Production/Achat/Admin, lecture ouverte à tous."""
    queryset = models.FamilleArticle.objects.all()
    serializer_class = serializers.FamilleArticleSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.MAGASINIER, Profil.COMMERCIAL, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["actif"]
    search_fields = ["nom"]


class FormatArticleViewSet(viewsets.ModelViewSet):
    """Liste déroulante des formats."""
    queryset = models.FormatArticle.objects.all()
    serializer_class = serializers.FormatArticleSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.MAGASINIER, Profil.COMMERCIAL, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["actif"]
    search_fields = ["valeur"]


class ParfumViewSet(viewsets.ModelViewSet):
    """Liste déroulante des parfums/variantes."""
    queryset = models.Parfum.objects.all()
    serializer_class = serializers.ParfumSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.MAGASINIER, Profil.COMMERCIAL, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["actif"]
    search_fields = ["nom"]


class UniteVenteArticleViewSet(viewsets.ModelViewSet):
    """Liste déroulante des unités de vente."""
    queryset = models.UniteVenteArticle.objects.all()
    serializer_class = serializers.UniteVenteArticleSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.MAGASINIER, Profil.COMMERCIAL, Profil.COMPTABILITE_DAF,),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["actif"]
    search_fields = ["nom"]



class ConversionUniteViewSet(viewsets.ModelViewSet):
    """Conversions centralisées (1 sac = 25 kg, 1 carton = 6 bouteilles...)."""
    queryset = models.ConversionUnite.objects.select_related("article")
    serializer_class = serializers.ConversionUniteSerializer
    permission_classes = [acces(
        lecture=(Profil.DIRECTION, Profil.RESPONSABLE_QUALITE, Profil.MAGASINIER, Profil.COMMERCIAL, Profil.COMPTABILITE_DAF,
                 Profil.AGENT_PRODUCTION),
        ecriture=(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI,),
    )]
    filterset_fields = ["article", "unite_source", "unite_cible"]

    @action(detail=False, methods=["get"])
    def convertir(self, request):
        """GET .../conversions/convertir/?quantite=2&de=SAC&vers=KG&article=<id>"""
        from apps.core.validation import convertir_decimal
        from django.core.exceptions import ValidationError
        article = models.Article.objects.filter(pk=request.query_params.get("article")).first()
        try:
            quantite = convertir_decimal(request.query_params.get("quantite"), "La quantité", strict=False)
            resultat = models.ConversionUnite.convertir(
                quantite, request.query_params.get("de"), request.query_params.get("vers"), article=article,
            )
        except (ValueError, ValidationError) as erreur:
            return Response({"erreur": getattr(erreur, "messages", [str(erreur)])[0]}, status=400)
        return Response({"quantite": quantite, "de": request.query_params.get("de"),
                         "vers": request.query_params.get("vers"), "resultat": resultat})
