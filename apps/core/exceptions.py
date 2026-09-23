"""
Gestionnaire d'exceptions DRF du projet (REST_FRAMEWORK["EXCEPTION_HANDLER"]).

Sans lui, une ValidationError Django levée dans un save() de modèle
remontait en erreur 500 sans message. Ici elle est transformée en 400
avec le message métier. Combiné à ATOMIC_REQUESTS, toute écriture
déjà faite pendant la requête est annulée (DRF appelle set_rollback()
pour toute exception qu'il gère).
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError, RestrictedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler, set_rollback

from .serializers import erreur_django_vers_drf


def gestionnaire_exceptions(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = erreur_django_vers_drf(exc)

    if isinstance(exc, (ProtectedError, RestrictedError)):
        set_rollback()
        objets = ", ".join(sorted({str(obj) for obj in list(exc.protected_objects if isinstance(exc, ProtectedError) else exc.restricted_objects)[:5]}))
        return Response(
            {"erreur": f"Suppression impossible : cet élément est encore utilisé par d'autres documents ({objets})."},
            status=status.HTTP_409_CONFLICT,
        )

    return exception_handler(exc, context)
