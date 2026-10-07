"""
Sérialiseurs DRF du module distribution.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class VehiculeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Vehicule
        fields = "__all__"


class ChauffeurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Chauffeur
        fields = "__all__"


class DepotSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Depot
        fields = "__all__"


class TourneeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Tournee
        fields = "__all__"


class PreparationLivraisonSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    # Le Magasinier ne lit pas les commandes : la préparation porte ce qu'il doit sortir.
    commande_numero = serializers.CharField(source="commande.numero", read_only=True)
    client_nom = serializers.CharField(source="commande.client.nom", read_only=True)
    depot_nom = serializers.CharField(source="depot.nom", read_only=True, default=None)
    lignes = serializers.SerializerMethodField()

    def get_lignes(self, preparation):
        """Articles à préparer (sans prix : le Magasinier n'en a pas besoin)."""
        return [
            {"article": l.article_id, "code": l.article.code, "designation": l.article.designation, "quantite": l.quantite}
            for l in preparation.commande.lignes.all()
        ]

    class Meta:
        model = models.PreparationLivraison
        fields = "__all__"
        extra_kwargs = {"lancee_par": {"required": False}}
        # Évolution uniquement via /confirmer_preparation/ et /confirmer_sortie/
        # (la sortie magasin mouvemente le stock).
        read_only_fields = ["lancee_par", "statut", "preparee_par", "date_confirmation_sortie"]


class BonLivraisonSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.BonLivraison
        fields = "__all__"
        read_only_fields = ["confirme_par", "date_livraison", "date_signature", "incident_livraison"]

    commande_numero = serializers.CharField(source="commande.numero", read_only=True)
    client_nom = serializers.CharField(source="commande.client.nom", read_only=True)
    client_adresse = serializers.CharField(source="commande.client.adresse", read_only=True)
    articles = serializers.SerializerMethodField()
    statut_paiement = serializers.SerializerMethodField()

    def get_articles(self, bon):
        return [
            {"code": l.article.code, "designation": l.article.designation, "quantite": l.quantite}
            for l in bon.commande.lignes.select_related("article")
        ]

    def get_statut_paiement(self, bon):
        facture = getattr(bon.commande, "facture", None)
        return facture.get_statut_display() if facture else "Non facturée"

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutLivraison.EN_LIVRAISON
        if valeur != actuel and valeur == models.StatutLivraison.LIVREE:
            raise serializers.ValidationError(
                "La livraison est confirmée uniquement par le Responsable Distribution (action /confirmer_livraison/)."
            )
        return valeur


class TransfertDepotSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.TransfertDepot
        fields = "__all__"

