# """
# Sérialiseurs DRF du module production.

# Chaque sérialiseur expose automatiquement tous les champs de son
# modèle (fields = "__all__") : les libellés visibles dans
# l'API (navigable browsable API de DRF) sont ceux définis en
# verbose_name dans models.py, donc déjà en français.
# """

# from rest_framework import serializers
# from . import models

# class PlanProductionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.PlanProduction
#         fields = "__all__"
#         extra_kwargs = {"cree_par": {"required": False}}


# class OrdreFabricationSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.OrdreFabrication
#         fields = "__all__"
#         extra_kwargs = {"responsable": {"required": False}}


# class BesoinMatierePrevuSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.BesoinMatierePrevu
#         fields = "__all__"


# class SortieMatiereSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.SortieMatiere
#         fields = "__all__"


# class RetourMatiereSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.RetourMatiere
#         fields = "__all__"


# class EtapeProductionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.EtapeProduction
#         fields = "__all__"
#         extra_kwargs = {"agent": {"required": False}}


# class PerteProductionSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.PerteProduction
#         fields = "__all__"



"""
Sérialiseurs DRF du module production.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin


def nom_utilisateur(utilisateur):
    """Nom lisible (nom complet, sinon identifiant) : évite d'afficher « #12 »."""
    if utilisateur is None:
        return None
    return utilisateur.get_full_name() or utilisateur.username


class SaisiParMixin(serializers.Serializer):
    saisi_par_nom = serializers.SerializerMethodField()

    def get_saisi_par_nom(self, instance):
        return nom_utilisateur(instance.saisi_par)
from . import models

class PlanProductionSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.PlanProduction
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        read_only_fields = ["cree_par"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutPlanProduction.PREVISION
        if valeur != actuel and valeur == models.StatutPlanProduction.CONVERTIE:
            raise serializers.ValidationError("Utilisez l'action /convertir_en_of/ pour convertir une prévision.")
        return valeur


class OrdreFabricationSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.OrdreFabrication
        fields = "__all__"
        extra_kwargs = {"responsable": {"required": False}}
        # Le statut n'évolue que par les actions /avancer_statut/ et /annuler/.
        read_only_fields = [
            "responsable", "statut", "motif_annulation", "date_debut_production", "date_fin",
        ]

    agents_affectes_noms = serializers.SerializerMethodField()

    def get_agents_affectes_noms(self, of):
        return [nom_utilisateur(agent) for agent in of.agents_affectes.all()]

    def validate_agents_affectes(self, agents):
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            models.OrdreFabrication.verifier_agents(agents)
        except DjangoValidationError as erreur:
            raise serializers.ValidationError(erreur.message_dict["agents_affectes"])
        return agents


class BesoinMatierePrevuSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.BesoinMatierePrevu
        fields = "__all__"


class DemandeMatiereSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True)
    matiere_code = serializers.CharField(source="matiere.code", read_only=True)
    matiere_designation = serializers.CharField(source="matiere.designation", read_only=True)
    demandeur_nom = serializers.SerializerMethodField()

    def get_demandeur_nom(self, demande):
        return nom_utilisateur(demande.demandeur)

    class Meta:
        model = models.DemandeMatiere
        fields = "__all__"
        extra_kwargs = {"demandeur": {"required": False}}
        # Les demandes sont générées depuis la composition de l'OF
        # (/ordres-fabrication/{id}/demander_matieres/) : OF, matière et
        # quantité ne se saisissent pas.
        read_only_fields = ["demandeur", "quantite_livree", "ordre_fabrication", "matiere", "quantite_demandee"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutDemandeMatiere.A_PREPARER
        if valeur != actuel and valeur in (
            models.StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION, models.StatutDemandeMatiere.PARTIELLEMENT_PREPAREE,
        ):
            raise serializers.ValidationError("La livraison se fait via l'action /livrer/ (qui génère la sortie matière).")
        return valeur


class DemandeComplementaireSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True)
    matiere_code = serializers.CharField(source="matiere.code", read_only=True)
    matiere_designation = serializers.CharField(source="matiere.designation", read_only=True)
    demandeur_nom = serializers.SerializerMethodField()

    def get_demandeur_nom(self, demande):
        return nom_utilisateur(demande.demandeur)

    class Meta:
        model = models.DemandeComplementaire
        fields = "__all__"
        extra_kwargs = {"demandeur": {"required": False}}
        # Traitement uniquement via les actions /approuver/ et /rejeter/.
        read_only_fields = ["demandeur", "statut"]


class SortieMatiereSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.SortieMatiere
        fields = "__all__"


class RetourMatiereSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.RetourMatiere
        fields = "__all__"


class SuiviProductionSerializer(ValidationModeleMixin, SaisiParMixin, serializers.ModelSerializer):
    class Meta:
        model = models.SuiviProduction
        fields = "__all__"
        read_only_fields = ["saisi_par"]


class SuiviEauSerializer(ValidationModeleMixin, SaisiParMixin, serializers.ModelSerializer):
    class Meta:
        model = models.SuiviEau
        fields = "__all__"
        read_only_fields = ["saisi_par"]


class EtapeProductionSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.EtapeProduction
        fields = "__all__"
        extra_kwargs = {"agent": {"required": False}}
        read_only_fields = ["agent"]

    agent_nom = serializers.SerializerMethodField()

    def get_agent_nom(self, etape):
        return nom_utilisateur(etape.agent)


class PerteProductionSerializer(ValidationModeleMixin, SaisiParMixin, serializers.ModelSerializer):
    class Meta:
        model = models.PerteProduction
        fields = "__all__"
        read_only_fields = ["saisi_par"]
