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
"""

from rest_framework import serializers
from . import models

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Client
        fields = "__all__"


class ProspectSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Prospect
        fields = "__all__"


class ContratClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ContratClient
        fields = "__all__"


class TarifSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Tarif
        fields = "__all__"


class CommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Commande
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}

    def validate(self, data):
        """
        Renvoie une erreur 400 propre AVANT d'atteindre Commande.save()
        (qui, lui, bloquerait quand même via ValidationError, mais en
        500 non catché s'il n'était pas intercepté ici). Couvre à la
        fois la création (client bloqué) et la mise à jour de statut
        (encours, une fois le montant réel connu).
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        client = data.get("client") or getattr(self.instance, "client", None)
        statut = data.get("statut", getattr(self.instance, "statut", models.StatutCommande.BROUILLON))

        if client and statut != models.StatutCommande.ANNULEE:
            montant = self.instance.montant_total if self.instance is not None else 0
            try:
                client.verifier_peut_commander(montant_commande=montant)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"client": e.messages})

        return data


class LigneCommandeSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LigneCommande
        fields = "__all__"

    def validate(self, data):
        """
        Une ligne ajoutée/modifiée après que la commande a quitté le
        brouillon peut faire dépasser l'encours du client : on
        revérifie ici pour un 400 propre (le save() de LigneCommande
        revérifie aussi côté modèle, en filet de sécurité).
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        commande = data.get("commande") or getattr(self.instance, "commande", None)
        if commande and commande.statut not in (
            models.StatutCommande.BROUILLON, models.StatutCommande.ANNULEE
        ):
            quantite = data.get("quantite", getattr(self.instance, "quantite", 0))
            prix = data.get("prix_unitaire", getattr(self.instance, "prix_unitaire", 0))
            montant_ligne_estime = quantite * prix

            autres_lignes = commande.lignes.all()
            if self.instance is not None:
                autres_lignes = autres_lignes.exclude(pk=self.instance.pk)
            montant_estime = sum((l.montant_ligne for l in autres_lignes), start=0) + montant_ligne_estime

            try:
                commande.client.verifier_peut_commander(montant_commande=montant_estime)
            except DjangoValidationError as e:
                raise serializers.ValidationError({"commande": e.messages})

        return data


class FactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Facture
        fields = "__all__"


class LigneFactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LigneFacture
        fields = "__all__"




class AvoirSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Avoir
        fields = "__all__"
        extra_kwargs = {"cree_par": {"required": False}}