"""
Vues du module référentiel.

Règle clé du cahier des charges : le Magasinier NE PEUT PAS créer ou
modifier une fiche technique. Seuls Responsable Production et
Administrateur SI le peuvent ; les autres profils sont en lecture
seule sur ce module.
"""

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
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION,),
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


class CompositionFicheTechniqueViewSet(viewsets.ModelViewSet):
    """Lignes de composition (matières et quantités par unité produite) : écriture ADMIN_SI uniquement."""
    queryset = models.CompositionFicheTechnique.objects.all()
    serializer_class = serializers.CompositionFicheTechniqueSerializer
    permission_classes = [acces(
        lecture=(Profil.RESPONSABLE_PRODUCTION,),
        ecriture=(Profil.ADMIN_SI,),
    )]
    filterset_fields = ["fiche_technique", "matiere"]


class FicheConditionnementViewSet(viewsets.ModelViewSet):
    queryset = models.FicheConditionnement.objects.all()
    serializer_class = serializers.FicheConditionnementSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
    filterset_fields = ["article"]




class ControleQualiteRequisViewSet(viewsets.ModelViewSet):
    queryset = models.ControleQualiteRequis.objects.all()
    serializer_class = serializers.ControleQualiteRequisSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_QUALITE, Profil.ADMIN_SI)]
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
