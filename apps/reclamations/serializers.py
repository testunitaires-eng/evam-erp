"""
Sérialiseurs DRF du module réclamations.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class ReclamationClientSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    # Le Commercial et la Distribution ne lisent pas les retours ni les
    # contrôles : état du retour recopié ici (la solution est refusée tant
    # que le retour est « En quarantaine »).
    retour_statut = serializers.CharField(source="retour_physique.statut", read_only=True, default=None)
    retour_statut_libelle = serializers.CharField(source="retour_physique.get_statut_display", read_only=True, default=None)
    retour_quantite = serializers.DecimalField(
        source="retour_physique.quantite_retournee", max_digits=12, decimal_places=3, read_only=True, default=None,
    )
    retour_date_reception = serializers.DateTimeField(source="retour_physique.date_reception", read_only=True, default=None)
    controle_resultat = serializers.CharField(source="retour_physique.controle.resultat", read_only=True, default=None)
    controle_resultat_libelle = serializers.CharField(
        source="retour_physique.controle.get_resultat_display", read_only=True, default=None,
    )
    solution_possible = serializers.SerializerMethodField()

    def get_solution_possible(self, reclamation):
        if reclamation.statut == models.StatutReclamation.CLOTUREE:
            return False
        retour = getattr(reclamation, "retour_physique", None)
        return retour is None or retour.statut != models.StatutRetourPhysique.EN_QUARANTAINE

    class Meta:
        model = models.ReclamationClient
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        read_only_fields = ["cree_par", "date_cloture", "produit_retourne"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutReclamation.OUVERTE
        if valeur != actuel and valeur == models.StatutReclamation.CLOTUREE:
            raise serializers.ValidationError("Une réclamation est clôturée automatiquement par l'enregistrement de sa solution client.")
        return valeur


class ReclamationAReceptionnerSerializer(serializers.ModelSerializer):
    """
    Vue réduite d'une réclamation pour le Magasinier et la Qualité, qui ne
    lisent pas les réclamations : de quoi rattacher un retour, sans prix
    ni description.
    """
    client_nom = serializers.CharField(source="client.nom", read_only=True)
    article_code = serializers.CharField(source="article.code", read_only=True)
    article_designation = serializers.CharField(source="article.designation", read_only=True)
    bon_livraison_numero = serializers.CharField(source="bon_livraison.numero", read_only=True, default=None)

    class Meta:
        model = models.ReclamationClient
        fields = [
            "id", "numero", "client", "client_nom", "article", "article_code", "article_designation",
            "quantite", "bon_livraison_numero", "statut", "date_creation",
        ]


class RetourPhysiqueSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    reclamation_numero = serializers.CharField(source="reclamation.numero", read_only=True)
    client_nom = serializers.CharField(source="reclamation.client.nom", read_only=True)
    article_code = serializers.CharField(source="reclamation.article.code", read_only=True)
    article_designation = serializers.CharField(source="reclamation.article.designation", read_only=True)
    lot_numero = serializers.CharField(source="lot.numero_lot", read_only=True, default=None)

    class Meta:
        model = models.RetourPhysique
        fields = "__all__"
        extra_kwargs = {"receptionne_par": {"required": False}}
        read_only_fields = ["receptionne_par", "statut"]


class ControleRetourSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    reclamation_numero = serializers.CharField(source="retour_physique.reclamation.numero", read_only=True)
    client_nom = serializers.CharField(source="retour_physique.reclamation.client.nom", read_only=True)
    article_code = serializers.CharField(source="retour_physique.reclamation.article.code", read_only=True)

    class Meta:
        model = models.ControleRetour
        fields = "__all__"
        extra_kwargs = {"controle_par": {"required": False}}
        read_only_fields = ["controle_par"]


class ReconditionnementSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Reconditionnement
        fields = "__all__"
        # Renseignés uniquement par l'action /terminer/ (qui réintègre le stock).
        read_only_fields = ["statut", "quantite_reconditionnee", "traite_par", "date_traitement"]


class CoutRetourPerteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.CoutRetourPerte
        fields = "__all__"
        # Remplis automatiquement par le circuit ; seul le coût du produit
        # détruit se valorise manuellement.
        read_only_fields = ["reclamation", "quantite_detruite", "cout_reconditionnement"]


class SolutionClientSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.SolutionClient
        fields = "__all__"
        extra_kwargs = {"autorise_par": {"required": False}}
        read_only_fields = ["autorise_par", "reference_sortie_caisse"]
