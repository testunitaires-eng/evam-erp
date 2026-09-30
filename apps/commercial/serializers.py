# """
# Sérialiseurs DRF du module commercial.

# Chaque sérialiseur expose automatiquement tous les champs de son
# modèle (fields = "__all__") : les libellés visibles dans
# l'API (navigable browsable API de DRF) sont ceux définis en
# verbose_name dans models.py, donc déjà en français.
# """

# from rest_framework import serializers
# from . import models

# class ClientSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Client
#         fields = "__all__"


# class ProspectSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Prospect
#         fields = "__all__"


# class ContratClientSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.ContratClient
#         fields = "__all__"


# class TarifSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Tarif
#         fields = "__all__"


# class CommandeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Commande
#         fields = "__all__"
#         extra_kwargs = {"cree_par": {"required": False}}


# class LigneCommandeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.LigneCommande
#         fields = "__all__"


# class FactureSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Facture
#         fields = "__all__"



# """
# Sérialiseurs DRF du module commercial.
# """

# from rest_framework import serializers
# from . import models

# class ClientSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Client
#         fields = "__all__"


# class ProspectSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Prospect
#         fields = "__all__"


# class ContratClientSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.ContratClient
#         fields = "__all__"


# class TarifSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Tarif
#         fields = "__all__"


# class CommandeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Commande
#         fields = "__all__"
#         extra_kwargs = {"cree_par": {"required": False}}


# class LigneCommandeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.LigneCommande
#         fields = "__all__"


# class FactureSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Facture
#         fields = "__all__"


# class LigneFactureSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.LigneFacture
#         fields = "__all__"




# class AvoirSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Avoir
#         fields = "__all__"
#         extra_kwargs = {"cree_par": {"required": False}}


# """
# Sérialiseurs DRF du module commercial.

# Chaque sérialiseur expose automatiquement tous les champs de son
# modèle (fields = "__all__") : les libellés visibles dans
# l'API (navigable browsable API de DRF) sont ceux définis en
# verbose_name dans models.py, donc déjà en français.
# """

# from rest_framework import serializers
# from . import models

# class ClientSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Client
#         fields = "__all__"


# class ProspectSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Prospect
#         fields = "__all__"


# class ContratClientSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.ContratClient
#         fields = "__all__"


# class TarifSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Tarif
#         fields = "__all__"


# class CommandeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Commande
#         fields = "__all__"
#         extra_kwargs = {"cree_par": {"required": False}}


# class LigneCommandeSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.LigneCommande
#         fields = "__all__"


# class FactureSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = models.Facture
#         fields = "__all__"



"""
Sérialiseurs DRF du module commercial.

Toutes les règles métier sont dans les clean() des modèles
(apps/commercial/models.py) et appliquées ici par
ValidationModeleMixin AVANT tout enregistrement : une règle non
respectée donne un 400 avec le message, jamais un enregistrement.
"""

from rest_framework import serializers
from apps.core.serializers import ValidationModeleMixin
from . import models


class ClientSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Client
        fields = "__all__"


class ProspectSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Prospect
        fields = "__all__"


class ContratClientSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.ContratClient
        fields = "__all__"


class TarifSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    class Meta:
        model = models.Tarif
        fields = "__all__"


class CommandeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """
    Client bloqué, encours dépassé, workflow de statut, commande sans
    ligne... : voir Commande.clean().
    """
    client_nom = serializers.CharField(source="client.nom", read_only=True)
    montant_total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    class Meta:
        model = models.Commande
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        read_only_fields = ["cree_par"]


class LigneCommandeSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """
    Encours, commande figée, quantité/prix positifs : voir LigneCommande.clean().
    stock_disponible : information (non bloquante) sur le stock produits
    finis disponible, affichée à la saisie de la ligne.
    """
    article_code = serializers.CharField(source="article.code", read_only=True)
    article_designation = serializers.CharField(source="article.designation", read_only=True)
    stock_disponible = serializers.SerializerMethodField()

    class Meta:
        model = models.LigneCommande
        fields = "__all__"

    def get_stock_disponible(self, ligne):
        from apps.stocks.models import StockArticle
        stock = StockArticle.objects.filter(article=ligne.article, depot__nom="Dépôt produits finis").first()
        return stock.quantite_disponible if stock else 0


class FactureSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """
    Les montants sont calculés à partir des lignes (generer_lignes) et
    le statut de paiement à partir des encaissements/avoirs : ils ne se
    saisissent pas. Seule l'annulation peut être demandée via `statut`.
    Le client est repris automatiquement de la commande.
    """
    class Meta:
        model = models.Facture
        fields = "__all__"
        extra_kwargs = {"client": {"required": False}}
        read_only_fields = ["montant_ht_total", "montant_taxes_total", "montant_total"]

    client_nom = serializers.CharField(source="client.nom", read_only=True)
    commande_numero = serializers.CharField(source="commande.numero", read_only=True)
    solde_restant = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutFacture.EMISE
        if valeur != actuel and valeur != models.StatutFacture.ANNULEE:
            raise serializers.ValidationError(
                "Le statut de paiement est calculé automatiquement d'après les encaissements ; "
                "seule l'annulation (ANNULEE) peut être demandée."
            )
        return valeur


class LigneFactureSerializer(serializers.ModelSerializer):
    article_code = serializers.CharField(source="article.code", read_only=True)
    article_designation = serializers.CharField(source="article.designation", read_only=True)

    class Meta:
        model = models.LigneFacture
        fields = "__all__"


class AvoirSerializer(ValidationModeleMixin, serializers.ModelSerializer):
    """Un avoir s'utilise via l'action /utiliser/ ; via `statut`, seule l'annulation est possible."""
    class Meta:
        model = models.Avoir
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}
        read_only_fields = ["cree_par", "facture_utilisation", "date_utilisation"]

    def validate_statut(self, valeur):
        actuel = self.instance.statut if self.instance is not None else models.StatutAvoir.EMIS
        if valeur != actuel and valeur != models.StatutAvoir.ANNULE:
            raise serializers.ValidationError(
                "Un avoir passe à « Utilisé » uniquement via l'action /utiliser/ ; "
                "seule l'annulation (ANNULE) peut être demandée ici."
            )
        return valeur
