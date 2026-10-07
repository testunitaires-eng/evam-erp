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


class SansDonneesFinancieresPourAgentMixin:
    """
    L'Agent Production ne voit aucune donnée financière (prix, montants) :
    ces champs sont retirés de la réponse quand c'est lui qui consulte.
    """
    CHAMPS_FINANCIERS = ("prix_unitaire", "montant", "montant_total_matieres")

    def to_representation(self, instance):
        donnees = super().to_representation(instance)
        requete = self.context.get("request")
        utilisateur = getattr(requete, "user", None)
        if utilisateur is not None and getattr(utilisateur, "profil", None) == "AGENT_PRODUCTION" and not utilisateur.is_superuser:
            for champ in self.CHAMPS_FINANCIERS:
                donnees.pop(champ, None)
        return donnees


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


class OrdreFabricationSerializer(SansDonneesFinancieresPourAgentMixin, ValidationModeleMixin, serializers.ModelSerializer):
    montant_total_matieres = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    activite_code = serializers.SerializerMethodField()
    usine_code = serializers.SerializerMethodField()
    ligne_code = serializers.CharField(source="ligne.code", read_only=True, default=None)
    circuit_code = serializers.CharField(source="circuit.code", read_only=True, default=None)
    etapes_prevues = serializers.SerializerMethodField()

    def get_activite_code(self, of):
        return of.activite.code if of.activite else None

    def get_usine_code(self, of):
        return of.usine.code if of.usine else None

    def get_etapes_prevues(self, of):
        """Étapes du circuit avec l'avancement saisi (quantités produites à l'étape)."""
        saisies_par_etape = {}
        for saisie in of.etapes.all():   # préchargé : aucune requête par étape
            saisies_par_etape.setdefault(saisie.etape, []).append(saisie)
        resultat = []
        for etape in of.etapes_prevues():
            saisies = saisies_par_etape.get(etape.etape.code, [])
            quantites = [s.quantite_produite for s in saisies if s.quantite_produite is not None]
            resultat.append({
                "ordre": etape.ordre, "code": etape.etape.code, "libelle": etape.etape.libelle,
                "obligatoire": etape.obligatoire, "poste": etape.poste.code if etape.poste_id else None,
                "machine": etape.equipement.code if etape.equipement_id else None,
                "saisies": len(saisies),
                "quantite_produite": sum(quantites) if quantites else None,
            })
        return resultat

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


class BesoinMatierePrevuSerializer(SansDonneesFinancieresPourAgentMixin, ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.BesoinMatierePrevu
        fields = "__all__"


class DemandeMatiereSerializer(SansDonneesFinancieresPourAgentMixin, ValidationModeleMixin, serializers.ModelSerializer):
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
        read_only_fields = [
            "demandeur", "quantite_livree", "ordre_fabrication", "matiere", "quantite_demandee",
            "prix_unitaire", "montant",
        ]

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
    heures_machine_effectives = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True, allow_null=True)

    class Meta:
        model = models.EtapeProduction
        fields = "__all__"
        extra_kwargs = {"agent": {"required": False}}
        read_only_fields = ["agent"]

    agent_nom = serializers.SerializerMethodField()

    def get_agent_nom(self, etape):
        return nom_utilisateur(etape.agent)


class PerteProductionSerializer(SansDonneesFinancieresPourAgentMixin, ValidationModeleMixin, SaisiParMixin, serializers.ModelSerializer):
    CHAMPS_FINANCIERS = ("valeur",)

    class Meta:
        model = models.PerteProduction
        fields = "__all__"
        read_only_fields = ["saisi_par"]


class ChangementSerieSerializer(SansDonneesFinancieresPourAgentMixin, ValidationModeleMixin, SaisiParMixin, serializers.ModelSerializer):
    CHAMPS_FINANCIERS = ("cout_nettoyage",)

    class Meta:
        model = models.ChangementSerie
        fields = "__all__"
        read_only_fields = ["saisi_par"]


class ConsommationLotMatiereSerializer(serializers.ModelSerializer):
    lot_numero = serializers.CharField(source="lot.numero", read_only=True)
    lot_fournisseur = serializers.CharField(source="lot.lot_fournisseur", read_only=True)
    matiere = serializers.CharField(source="lot.article.code", read_only=True)
    of = serializers.CharField(source="sortie.ordre_fabrication.numero", read_only=True)

    class Meta:
        model = models.ConsommationLotMatiere
        fields = "__all__"


class ParametreProductionSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ParametreProduction
        exclude = ["id"]


class EvenementProductionSerializer(ValidationModeleMixin, SaisiParMixin, serializers.ModelSerializer):
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True)

    class Meta:
        model = models.EvenementProduction
        fields = "__all__"
        read_only_fields = ["saisi_par"]
