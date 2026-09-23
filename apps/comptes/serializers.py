"""
Sérialiseurs DRF du module comptes.
"""

from rest_framework import serializers
from . import models


class UtilisateurSerializer(serializers.ModelSerializer):
    """
    Expose explicitement les champs (plutôt que "__all__") pour ne
    jamais renvoyer le mot de passe haché, et pour exposer le champ
    Django natif `is_active` sous son nom métier français `actif`.
    """
    actif = serializers.BooleanField(source="is_active", read_only=True)

    class Meta:
        model = models.Utilisateur
        fields = [
            "id", "username", "password", "first_name", "last_name", "email",
            "profil", "telephone", "actif", "date_creation",
            "desactive_par", "date_desactivation",
        ]
        extra_kwargs = {
            "password": {"write_only": True},
            "desactive_par": {"read_only": True},
            "date_desactivation": {"read_only": True},
        }

    def validate_password(self, mot_de_passe):
        """Applique les règles de robustesse de AUTH_PASSWORD_VALIDATORS (settings.py)."""
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(mot_de_passe, user=self.instance)
        except DjangoValidationError as erreur:
            raise serializers.ValidationError(erreur.messages)
        return mot_de_passe

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Le mot de passe est obligatoire à la création du compte."})
        return attrs

    def create(self, validated_data):
        """Hache le mot de passe correctement (create() ne le fait pas par défaut)."""
        mot_de_passe = validated_data.pop("password", None)
        utilisateur = models.Utilisateur(**validated_data)
        if mot_de_passe:
            utilisateur.set_password(mot_de_passe)
        utilisateur.save()
        return utilisateur

    def update(self, instance, validated_data):
        mot_de_passe = validated_data.pop("password", None)
        utilisateur = super().update(instance, validated_data)
        if mot_de_passe:
            utilisateur.set_password(mot_de_passe)
            utilisateur.save()
        return utilisateur


class JournalActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.JournalAction
        fields = "__all__"
