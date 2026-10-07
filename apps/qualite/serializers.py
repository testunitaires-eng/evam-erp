"""
Sérialiseurs DRF du module qualite.

Chaque sérialiseur expose automatiquement tous les champs de son
modèle (fields = "__all__") : les libellés visibles dans
l'API (navigable browsable API de DRF) sont ceux définis en
verbose_name dans models.py, donc déjà en français.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models

class LotSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Lot
        fields = "__all__"
        # Le statut évolue uniquement par le contrôle qualité et les
        # actions /liberer/ et /bloquer/ (la libération fait entrer le lot
        # en stock : la contourner donnerait un lot "libéré" hors stock).
        read_only_fields = ["statut"]


class ControleQualiteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ControleQualite
        fields = "__all__"
        extra_kwargs = {"controleur": {"required": False}}
        read_only_fields = ["controleur"]



class ParametreQualiteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ParametreQualite
        fields = "__all__"


class InstrumentSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    prochaine_echeance = serializers.DateField(read_only=True)
    etalonnage_valide = serializers.BooleanField(read_only=True)

    class Meta:
        model = models.Instrument
        fields = "__all__"


class PointControleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    parametre_libelle = serializers.CharField(source="parametre.libelle", read_only=True)
    unite = serializers.CharField(source="parametre.unite", read_only=True)
    activite_code = serializers.CharField(source="activite.code", read_only=True, default=None)
    etape_libelle = serializers.CharField(source="etape.libelle", read_only=True, default=None)

    class Meta:
        model = models.PointControle
        fields = "__all__"
        read_only_fields = ["version"]


class PieceJointeQualiteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.PieceJointeQualite
        fields = "__all__"
        read_only_fields = ["ajoute_par"]


class ResultatControleSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    controle = serializers.CharField(source="point.designation", read_only=True)
    parametre = serializers.CharField(source="point.parametre.libelle", read_only=True)
    unite = serializers.CharField(source="point.parametre.unite", read_only=True)
    type_resultat = serializers.CharField(source="point.parametre.type_resultat", read_only=True)
    critere = serializers.SerializerMethodField()
    bloquant = serializers.BooleanField(source="point.bloquant", read_only=True)
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True, default=None)
    lot_numero = serializers.CharField(source="lot.numero_lot", read_only=True, default=None)
    lot_matiere_numero = serializers.CharField(source="lot_matiere.numero", read_only=True, default=None)
    operateur_nom = serializers.SerializerMethodField()
    en_retard = serializers.SerializerMethodField()
    pieces_jointes = PieceJointeQualiteSerializer(many=True, read_only=True)

    class Meta:
        model = models.ResultatControle
        fields = "__all__"
        # Le résultat se saisit par l'action /enregistrer/ (conformité calculée) ;
        # à la création, on ne choisit que le contrôle et son rattachement.
        read_only_fields = [
            "statut", "date_realisation", "valeur", "resultat_qualitatif", "conforme", "operateur", "valide_par",
            "est_reprise", "controle_origine",
        ]

    def get_critere(self, resultat):
        point = resultat.point
        morceaux = []
        if point.valeur_min is not None:
            morceaux.append(f"min {point.valeur_min.normalize()}")
        if point.valeur_max is not None:
            morceaux.append(f"max {point.valeur_max.normalize()}")
        if point.valeur_cible is not None:
            morceaux.append(f"cible {point.valeur_cible.normalize()}" + (f" ± {point.tolerance.normalize()}" if point.tolerance is not None else ""))
        return ", ".join(morceaux) or None

    def get_operateur_nom(self, resultat):
        utilisateur = resultat.operateur
        return (utilisateur.get_full_name() or utilisateur.username) if utilisateur else None

    def get_en_retard(self, resultat):
        from django.utils import timezone
        return resultat.statut in models.STATUTS_EN_ATTENTE and bool(resultat.date_prevue) and resultat.date_prevue < timezone.now()


class NonConformiteSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    controle_numero = serializers.CharField(source="resultat.numero", read_only=True, default=None)
    of_numero = serializers.CharField(source="ordre_fabrication.numero", read_only=True, default=None)
    lot_numero = serializers.CharField(source="lot.numero_lot", read_only=True, default=None)
    pieces_jointes = PieceJointeQualiteSerializer(many=True, read_only=True)

    class Meta:
        model = models.NonConformite
        fields = "__all__"
        read_only_fields = ["statut", "decision", "ouverte_par", "cloturee_par", "date_cloture"]
