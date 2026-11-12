from decimal import Decimal

from rest_framework import serializers

from apps.core.serializers import ValidationModeleMixin
from . import models


class VersionneeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    figee = serializers.BooleanField(read_only=True)
    saisi_par_nom = serializers.CharField(source="saisi_par.username", read_only=True, default=None)


class ParametresEauSerializer(VersionneeSerializer):
    usine_code = serializers.CharField(source="usine.code", read_only=True)

    class Meta:
        model = models.ParametresEau
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class CaracteristiquesEquipementSerializer(VersionneeSerializer):
    equipement_code = serializers.CharField(source="equipement.code", read_only=True)
    equipement_designation = serializers.CharField(source="equipement.designation", read_only=True)
    bloc = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = models.CaracteristiquesEquipement
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class PrevisionVolumeSerializer(VersionneeSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True)
    volume_m3 = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = models.PrevisionVolume
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class PrevisionCaptageSerializer(VersionneeSerializer):
    part_site_eau = serializers.DecimalField(max_digits=9, decimal_places=6, read_only=True)

    class Meta:
        model = models.PrevisionCaptage
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class ElementCoutSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    bloc = serializers.CharField(read_only=True, allow_null=True)
    etape_libelle = serializers.CharField(source="etape.libelle", read_only=True)
    equipement_code = serializers.CharField(source="equipement.code", read_only=True, default=None)

    class Meta:
        model = models.ElementCout
        fields = "__all__"


class VersionElementCoutSerializer(VersionneeSerializer):
    element_libelle = serializers.CharField(source="element.libelle", read_only=True)
    famille = serializers.CharField(source="element.famille", read_only=True)

    class Meta:
        model = models.VersionElementCout
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class CoutStandardEauSerializer(serializers.ModelSerializer):
    usine_code = serializers.CharField(source="usine.code", read_only=True)
    cout_litre = serializers.DecimalField(max_digits=14, decimal_places=7, read_only=True)
    propose_par_nom = serializers.CharField(source="propose_par.username", read_only=True, default=None)
    valide_par_nom = serializers.CharField(source="valide_par.username", read_only=True, default=None)

    class Meta:
        model = models.CoutStandardEau
        fields = "__all__"
        read_only_fields = [champ.name for champ in models.CoutStandardEau._meta.fields]


# Phase 3 - saisies du traitement de l'eau

class CompteurSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Compteur
        fields = "__all__"


class SaisieSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    saisi_par_nom = serializers.CharField(source="saisi_par.username", read_only=True, default=None)


class ReleveCompteurSerializer(SaisieSerializer):
    compteur_code = serializers.CharField(source="compteur.code", read_only=True)

    class Meta:
        model = models.ReleveCompteur
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class ExceptionHeuresSerializer(SaisieSerializer):
    class Meta:
        model = models.ExceptionHeures
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class RelevePressionSerializer(SaisieSerializer):
    equipement_code = serializers.CharField(source="equipement.code", read_only=True)
    pression_max = serializers.DecimalField(max_digits=8, decimal_places=3, read_only=True, allow_null=True)
    au_dessus_du_seuil = serializers.BooleanField(read_only=True)

    class Meta:
        model = models.RelevePression
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]


class PerteEauSerializer(SaisieSerializer):
    volume_m3 = serializers.DecimalField(max_digits=12, decimal_places=3, read_only=True, allow_null=True)

    class Meta:
        model = models.PerteEau
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]
        extra_kwargs = {"type_perte": {"required": False}}


# Phase 4 - maintenance

class InterventionSerializer(SaisieSerializer):
    equipement_code = serializers.CharField(source="equipement.code", read_only=True)
    operation_libelle = serializers.CharField(source="operation.libelle", read_only=True, default=None)
    element_remplace_libelle = serializers.CharField(source="element_remplace.libelle", read_only=True, default=None)
    nouvelle_piece_enregistree = serializers.SerializerMethodField()

    class Meta:
        model = models.Intervention
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]

    def get_nouvelle_piece_enregistree(self, intervention):
        if intervention.type_intervention != models.TypeIntervention.REMPLACEMENT:
            return None
        return intervention.installations.exists()


class InstallationSerializer(SaisieSerializer):
    """Lots étalés : avec les prix, réservé au contrôle de gestion et aux consultants."""
    element_libelle = serializers.CharField(source="element.libelle", read_only=True)
    dernier_mois = serializers.CharField(read_only=True)
    mois_deja_etales = serializers.IntegerField(read_only=True, allow_null=True)
    valeur_residuelle = serializers.SerializerMethodField()
    montant_etale_mensuel = serializers.SerializerMethodField()

    class Meta:
        model = models.Installation
        fields = "__all__"
        read_only_fields = ["saisi_par", "date_saisie"]

    def get_valeur_residuelle(self, lot):
        valeur = lot.valeur_residuelle
        return None if valeur is None else str(valeur.quantize(Decimal("0.01")))

    def get_montant_etale_mensuel(self, lot):
        """Étalement du lot à son mois d'installation (prix x quantité ÷ durée de vie)."""
        return str(models.montant_mensuel_etale(lot.quantite, lot.prix_unitaire, lot.duree_vie_mois).quantize(Decimal("0.01")))
