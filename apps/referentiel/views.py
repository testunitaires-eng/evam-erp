"""
Vues du module référentiel.

Les droits (qui peut consulter/créer/modifier) sont désormais définis
par la matrice de droits (module REFERENTIEL), configurable par
l'Administrateur SI sans toucher au code. Voir
apps/comptes/management/commands/initialiser_matrice_droits.py pour
les valeurs de départ (ex : le Magasinier a peut_consulter=True mais
peut_creer=False et peut_modifier=False sur ce module).
"""

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from apps.comptes.permissions import droit_matrice
from apps.comptes.models import Module


class ArticleViewSet(viewsets.ModelViewSet):
    queryset = models.Article.objects.all()
    serializer_class = serializers.ArticleSerializer
    permission_classes = [droit_matrice(Module.REFERENTIEL)]
    filterset_fields = ["type_article", "famille", "actif"]
    search_fields = ["code", "designation"]


class FicheTechniqueViewSet(viewsets.ModelViewSet):
    queryset = models.FicheTechnique.objects.all()
    serializer_class = serializers.FicheTechniqueSerializer
    permission_classes = [droit_matrice(Module.REFERENTIEL)]
    filterset_fields = ["article", "statut"]

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        """
        POST /api/referentiel/fiches-techniques/{id}/valider/
        Fait passer la fiche de BROUILLON à VALIDEE.
        Nécessite peut_valider=True sur le module REFERENTIEL.
        """
        from apps.comptes.permissions import a_le_droit
        if not a_le_droit(request.user, Module.REFERENTIEL, "peut_valider"):
            return Response({"erreur": "Votre profil ne peut pas valider de fiche technique."}, status=403)
        fiche = self.get_object()
        try:
            fiche.valider(request.user)
        except ValueError as erreur:
            return Response({"erreur": str(erreur)}, status=400)
        return Response(self.get_serializer(fiche).data)


class CompositionFicheTechniqueViewSet(viewsets.ModelViewSet):
    queryset = models.CompositionFicheTechnique.objects.all()
    serializer_class = serializers.CompositionFicheTechniqueSerializer
    permission_classes = [droit_matrice(Module.REFERENTIEL)]
    filterset_fields = ["fiche_technique", "matiere"]


class FicheConditionnementViewSet(viewsets.ModelViewSet):
    queryset = models.FicheConditionnement.objects.all()
    serializer_class = serializers.FicheConditionnementSerializer
    permission_classes = [droit_matrice(Module.REFERENTIEL)]
    filterset_fields = ["article"]
