"""
Historique automatique des documents (onglet « Historique » de chaque
tiroir) : création et chaque changement de statut, avec qui, quand,
ancien -> nouveau statut. Alimenté par ValidationAvantEnregistrement.save()
pour TOUT modèle qui a un champ `statut` : aucun oubli possible, quelle
que soit la voie (API, action métier, admin Django, code interne).

L'utilisateur est retrouvé via la requête HTTP en cours (voir
UtilisateurCourantMiddleware). Hors requête (commande, migration), il
est enregistré vide : « Système ».
"""

import threading

_courant = threading.local()


class UtilisateurCourantMiddleware:
    """Mémorise la requête en cours ; DRF y place l'utilisateur authentifié (JWT)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _courant.requete = request
        try:
            return self.get_response(request)
        finally:
            _courant.requete = None


def utilisateur_courant():
    requete = getattr(_courant, "requete", None)
    utilisateur = getattr(requete, "user", None)
    if utilisateur is not None and utilisateur.is_authenticated:
        return utilisateur
    return None


def libelle_statut(instance, valeur):
    if valeur is None:
        return ""
    choix = dict(type(instance)._meta.get_field("statut").flatchoices)
    return str(choix.get(valeur, valeur))


def enregistrer_historique(instance, ancien_statut):
    """Ajoute une ligne d'historique pour une création ou un changement de statut."""
    from django.contrib.contenttypes.models import ContentType
    from .models import Historique
    Historique.objects.create(
        content_type=ContentType.objects.get_for_model(type(instance)),
        objet_id=instance.pk,
        reference=str(getattr(instance, "numero", "") or getattr(instance, "numero_lot", "") or instance.pk),
        action="Création" if ancien_statut is None else "Changement de statut",
        ancien_statut=libelle_statut(instance, ancien_statut),
        nouveau_statut=libelle_statut(instance, instance.statut),
        utilisateur=utilisateur_courant(),
    )
    from .notifications import notifier_changement_statut
    notifier_changement_statut(instance)
