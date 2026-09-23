"""
Vues du module référentiel.

Règle clé du cahier des charges : le Magasinier NE PEUT PAS créer ou
modifier une fiche technique. Seuls Responsable Production et
Administrateur SI le peuvent ; les autres profils sont en lecture
seule sur ce module.
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import role_required, lecture_seule_pour
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
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)]
    filterset_fields = ["type_article", "famille", "actif"]
    search_fields = ["code", "designation"]

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


class FicheTechniqueViewSet(viewsets.ModelViewSet):
    queryset = models.FicheTechnique.objects.all()
    serializer_class = serializers.FicheTechniqueSerializer
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
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


class CompositionFicheTechniqueViewSet(viewsets.ModelViewSet):
    queryset = models.CompositionFicheTechnique.objects.all()
    serializer_class = serializers.CompositionFicheTechniqueSerializer
    permission_classes = [role_required(Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI)]
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
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)]
    filterset_fields = ["actif"]
    search_fields = ["nom"]


class FormatArticleViewSet(viewsets.ModelViewSet):
    """Liste déroulante des formats."""
    queryset = models.FormatArticle.objects.all()
    serializer_class = serializers.FormatArticleSerializer
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)]
    filterset_fields = ["actif"]
    search_fields = ["valeur"]


class ParfumViewSet(viewsets.ModelViewSet):
    """Liste déroulante des parfums/variantes."""
    queryset = models.Parfum.objects.all()
    serializer_class = serializers.ParfumSerializer
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)]
    filterset_fields = ["actif"]
    search_fields = ["nom"]


class UniteVenteArticleViewSet(viewsets.ModelViewSet):
    """Liste déroulante des unités de vente."""
    queryset = models.UniteVenteArticle.objects.all()
    serializer_class = serializers.UniteVenteArticleSerializer
    permission_classes = [lecture_seule_pour(Profil.RESPONSABLE_PRODUCTION, Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI)]
    filterset_fields = ["actif"]
    search_fields = ["nom"]
