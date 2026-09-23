"""
Mixin de sérialiseur partagé : applique les règles métier du modèle
(sa méthode clean()) pendant la validation DRF, AVANT tout
enregistrement. Une règle non respectée donne un 400 avec le message
exact, jamais un enregistrement partiel ni une erreur 500.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


def erreur_django_vers_drf(erreur):
    """Convertit une ValidationError Django en ValidationError DRF lisible par le frontend."""
    if hasattr(erreur, "error_dict"):
        return serializers.ValidationError(erreur.message_dict)
    return serializers.ValidationError({"erreur": erreur.messages})


class ValidationModeleMixin:
    """
    À placer AVANT serializers.ModelSerializer dans l'héritage.

    Construit l'objet tel qu'il serait après enregistrement (copie
    relue en base pour une modification, nouvel objet pour une
    création), puis appelle son clean(). Les champs renseignés par la
    vue elle-même (cree_par, utilisateur...) ne sont pas encore connus
    ici : ils sont revérifiés au save() du modèle
    (ValidationAvantEnregistrement).
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        modele = self.Meta.model
        if self.instance is not None:
            instance = modele._default_manager.get(pk=self.instance.pk)
        else:
            instance = modele()
        champs_m2m = {champ.name for champ in modele._meta.many_to_many}
        for champ, valeur in attrs.items():
            if champ not in champs_m2m:
                setattr(instance, champ, valeur)
        try:
            instance.clean()
        except DjangoValidationError as erreur:
            raise erreur_django_vers_drf(erreur)
        return attrs
