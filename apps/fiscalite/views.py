"""
Vues du module fiscalité.

Lecture ouverte à tout profil authentifié (le Commercial doit pouvoir
voir quel code fiscal s'applique à un article avant de vendre) ;
écriture réservée à Comptabilité/DAF et Administrateur SI - JAMAIS au
Commercial ni au Caissier (règle du document : "le vendeur ne choisit
jamais manuellement le taux de TVA").
"""

from rest_framework import viewsets
from . import models, serializers
from apps.comptes.permissions import lecture_seule_pour
from apps.comptes.models import Profil


class CodeFiscalViewSet(viewsets.ModelViewSet):
    queryset = models.CodeFiscal.objects.all()
    serializer_class = serializers.CodeFiscalSerializer
    permission_classes = [lecture_seule_pour(Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)]
    filterset_fields = ["actif", "exonere", "sfec_actif"]
    search_fields = ["code", "famille_fiscale"]