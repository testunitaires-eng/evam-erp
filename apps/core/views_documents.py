"""
Paramétrage des documents imprimés : identité de l'entreprise et logo.

GET   /api/documents/entreprise/        identité (tous les profils connectés)
PATCH /api/documents/entreprise/        modification (Admin SI, Direction, DAF)
GET   /api/documents/entreprise/logo/   le logo (image)
POST  /api/documents/entreprise/logo/   envoi du logo (multipart, champ « logo » : PNG ou JPEG, 2 Mo max)
DELETE /api/documents/entreprise/logo/  suppression du logo
GET   /api/documents/apercu/            PDF d'exemple pour contrôler la mise en page
"""

from django.http import HttpResponse
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.comptes.models import Profil
from .models import ParametreEntreprise
from .serializers import ParametreEntrepriseSerializer

PROFILS_PARAMETRAGE = (Profil.ADMIN_SI, Profil.DIRECTION, Profil.COMPTABILITE_DAF)
TYPES_LOGO = {"image/png": "image/png", "image/jpeg": "image/jpeg", "image/jpg": "image/jpeg"}
TAILLE_MAX_LOGO = 2 * 1024 * 1024


def _peut_modifier(utilisateur):
    return utilisateur.is_superuser or utilisateur.profil in PROFILS_PARAMETRAGE


@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def entreprise(request):
    parametre = ParametreEntreprise.courant()
    if request.method == "GET":
        return Response(ParametreEntrepriseSerializer(parametre).data)
    if not _peut_modifier(request.user):
        return Response({"erreur": "Seuls l'Administrateur SI, la Direction et la DAF modifient l'identité de l'entreprise."}, status=403)
    serializer = ParametreEntrepriseSerializer(parametre, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def logo(request):
    parametre = ParametreEntreprise.courant()
    if request.method == "GET":
        if not parametre.logo:
            return Response({"erreur": "Aucun logo enregistré."}, status=404)
        return HttpResponse(bytes(parametre.logo), content_type=parametre.logo_type or "image/png")
    if not _peut_modifier(request.user):
        return Response({"erreur": "Seuls l'Administrateur SI, la Direction et la DAF modifient le logo."}, status=403)
    if request.method == "DELETE":
        parametre.logo, parametre.logo_type = None, ""
        parametre.save()
        return Response(status=204)
    fichier = request.FILES.get("logo")
    if fichier is None:
        return Response({"erreur": "Envoyez le fichier dans le champ « logo » (multipart/form-data)."}, status=400)
    type_contenu = TYPES_LOGO.get((fichier.content_type or "").lower())
    if type_contenu is None:
        return Response({"erreur": "Le logo doit être une image PNG ou JPEG."}, status=400)
    if fichier.size > TAILLE_MAX_LOGO:
        return Response({"erreur": "Le logo ne doit pas dépasser 2 Mo."}, status=400)
    contenu = fichier.read()
    try:
        from io import BytesIO
        from PIL import Image as ImagePIL
        ImagePIL.open(BytesIO(contenu)).verify()
    except Exception:
        return Response({"erreur": "Ce fichier n'est pas une image lisible."}, status=400)
    parametre.logo, parametre.logo_type = contenu, type_contenu
    parametre.save()
    return Response(ParametreEntrepriseSerializer(parametre).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def apercu(request):
    """Document d'exemple : vérifier le logo, les couleurs et les mentions avant d'imprimer de vrais documents."""
    from django.utils import timezone
    from .pdf import DocumentPDF, montant, telecharger
    document = DocumentPDF("APERÇU", "EXEMPLE-000001", timezone.now(), request.user, filigrane="EXEMPLE")
    document.avec_tiers("Client", ["Nom du client", "Adresse du client", "IFU 0000000000000"],
                        "Références", ["Commande : CMD-000001", "Échéance : 30 jours"])
    document.avec_lignes(["Code", "Désignation", "Qté", "P.U. HT", "Montant HT"],
                         [["EAU70P8", "Eau 70 cl - Pack de 8", "10", montant(1500), montant(15000)]],
                         [24, None, 16, 26, 28], colonnes_nombres=(2, 3, 4))
    document.avec_totaux([("Total HT", montant(15000)), ("TVA 18 %", montant(2700)), ("Net à payer TTC (FCFA)", montant(17700))],
                         en_lettres_de=17700)
    document.avec_texte(document.entreprise.conditions_paiement)
    document.avec_signatures("Le client", f"Pour {document.entreprise.raison_sociale}")
    return document.reponse("apercu-document", telecharger(request))
