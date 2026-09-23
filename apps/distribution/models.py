"""
Module 9 - Distribution, logistique et livraison.

Reproduit exactement le circuit décrit en §12.3 du cahier des charges :
commande validée -> Responsable Distribution lance la préparation ->
Magasinier prépare -> Magasinier confirme la sortie -> bon de
livraison généré -> Chauffeur livre -> client signe -> Responsable
Distribution confirme la livraison.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur
from apps.commercial.models import Commande, StatutCommande
from apps.core.models import generer_numero
from apps.core.validation import ValidationAvantEnregistrement, valeur_en_base, verifier_transition


class Vehicule(models.Model):
    immatriculation = models.CharField("Immatriculation", max_length=30, unique=True)
    type_vehicule = models.CharField("Type de véhicule", max_length=100, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Véhicule"
        verbose_name_plural = "Véhicules"

    def __str__(self):
        return self.immatriculation


class Chauffeur(models.Model):
    utilisateur = models.OneToOneField(
        Utilisateur, verbose_name="Utilisateur", on_delete=models.CASCADE,
        related_name="fiche_chauffeur",
    )
    permis_numero = models.CharField("Numéro de permis", max_length=50, blank=True)

    class Meta:
        verbose_name = "Chauffeur"
        verbose_name_plural = "Chauffeurs"

    def __str__(self):
        return str(self.utilisateur)


class Depot(models.Model):
    """Dépôt logistique (peut correspondre à apps.stocks.Depot ; séparé
    ici pour ne pas créer de dépendance circulaire entre modules)."""
    nom = models.CharField("Nom", max_length=100)

    class Meta:
        verbose_name = "Dépôt (distribution)"
        verbose_name_plural = "Dépôts (distribution)"

    def __str__(self):
        return self.nom


class Tournee(ValidationAvantEnregistrement, models.Model):
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    chauffeur = models.ForeignKey(Chauffeur, verbose_name="Chauffeur", on_delete=models.PROTECT)
    vehicule = models.ForeignKey(Vehicule, verbose_name="Véhicule", on_delete=models.PROTECT)
    date_tournee = models.DateField("Date de la tournée")

    class Meta:
        verbose_name = "Tournée"
        verbose_name_plural = "Tournées"

    def __str__(self):
        return f"{self.numero} - {self.date_tournee}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("TRN")
        super().save(*args, **kwargs)

    def clean(self):
        if self.vehicule_id and not self.vehicule.actif:
            raise ValidationError({"vehicule": f"Le véhicule {self.vehicule.immatriculation} est inactif."})
        if self.chauffeur_id and not self.chauffeur.utilisateur.is_active:
            raise ValidationError({"chauffeur": "Le compte de ce chauffeur est désactivé."})


class StatutPreparation(models.TextChoices):
    A_PREPARER = "A_PREPARER", "À préparer"
    EN_PREPARATION = "EN_PREPARATION", "En préparation"
    PRETE = "PRETE", "Prête"
    SORTIE_MAGASIN = "SORTIE_MAGASIN", "Sortie magasin"


class PreparationLivraison(ValidationAvantEnregistrement, models.Model):
    """
    Étape 1 du circuit (§12.3, points 6-9) : le Responsable Distribution
    lance la préparation, le Magasinier prépare puis confirme la sortie.
    """
    commande = models.OneToOneField(
        Commande, verbose_name="Commande", on_delete=models.PROTECT,
        related_name="preparation",
    )
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutPreparation.choices,
        default=StatutPreparation.A_PREPARER,
    )
    lancee_par = models.ForeignKey(
        Utilisateur, verbose_name="Préparation lancée par (Resp. Distribution)",
        on_delete=models.PROTECT, related_name="preparations_lancees",
    )
    preparee_par = models.ForeignKey(
        Utilisateur, verbose_name="Préparée par (Magasinier)",
        on_delete=models.PROTECT, related_name="preparations_faites",
        null=True, blank=True,
    )
    date_lancement = models.DateTimeField("Date de lancement", auto_now_add=True)
    date_confirmation_sortie = models.DateTimeField("Date de sortie magasin", null=True, blank=True)

    class Meta:
        verbose_name = "Préparation de livraison"
        verbose_name_plural = "Préparations de livraison"

    def __str__(self):
        return f"Préparation {self.commande.numero} ({self.get_statut_display()})"

    TRANSITIONS = {
        StatutPreparation.A_PREPARER: {StatutPreparation.EN_PREPARATION},
        StatutPreparation.EN_PREPARATION: {StatutPreparation.PRETE, StatutPreparation.SORTIE_MAGASIN},
        StatutPreparation.PRETE: {StatutPreparation.SORTIE_MAGASIN},
    }

    def clean(self):
        """
        - on ne prépare qu'une commande validée (ou déjà en préparation)
          ayant au moins une ligne ;
        - la commande ne change plus après le lancement ;
        - le statut suit : À préparer -> En préparation -> (Prête) ->
          Sortie magasin ; une préparation sortie du magasin est figée.
        """
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutPreparation.SORTIE_MAGASIN:
            raise ValidationError("Cette préparation est déjà sortie du magasin : elle ne peut plus être modifiée.")
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de préparation",
            initial=StatutPreparation.A_PREPARER,
        )
        if self.pk and valeur_en_base(self, "commande") != self.commande_id:
            raise ValidationError({"commande": "La commande d'une préparation ne peut pas être changée."})
        if ancien_statut is None and self.commande_id:
            commande = self.commande
            if commande.statut not in (StatutCommande.VALIDEE, StatutCommande.EN_PREPARATION):
                raise ValidationError({"commande": (
                    f"La commande {commande.numero} est {commande.get_statut_display().lower()} : "
                    "seule une commande validée peut être préparée."
                )})
            if not commande.lignes.exists():
                raise ValidationError({"commande": f"La commande {commande.numero} n'a aucune ligne à préparer."})

    def verifier_suppression(self):
        if self.statut == StatutPreparation.SORTIE_MAGASIN:
            raise ValidationError("Une préparation sortie du magasin ne peut pas être supprimée (le stock a été mouvementé).")

    @transaction.atomic
    def confirmer_sortie(self, utilisateur):
        """
        Le Magasinier confirme la sortie magasin : sortie de stock de
        chaque ligne de la commande, le tout ou rien (si un article
        manque en stock, AUCUNE sortie n'est enregistrée et la
        préparation ne change pas de statut).
        """
        from django.utils import timezone
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        if self.statut not in (StatutPreparation.EN_PREPARATION, StatutPreparation.PRETE):
            raise ValueError(
                f"Préparation « {self.get_statut_display()} » : la sortie magasin n'est possible "
                "qu'après confirmation de la préparation."
            )
        if self.commande.statut == StatutCommande.ANNULEE:
            raise ValueError(f"La commande {self.commande.numero} a été annulée : sortie impossible.")
        self.statut = StatutPreparation.SORTIE_MAGASIN
        self.date_confirmation_sortie = timezone.now()
        self.save()
        depot_pf = depot_par_defaut("Dépôt produits finis")
        for ligne in self.commande.lignes.all():
            MouvementStock.objects.create(
                article=ligne.article,
                depot=depot_pf,
                type_mouvement=TypeMouvement.SORTIE,
                quantite=ligne.quantite,
                motif=f"Sortie magasin pour livraison - commande {self.commande.numero}",
                document_origine=self.commande.numero,
                utilisateur=utilisateur,
            )


class StatutLivraison(models.TextChoices):
    EN_LIVRAISON = "EN_LIVRAISON", "En livraison"
    LIVREE = "LIVREE", "Livrée"
    PARTIELLEMENT_LIVREE = "PARTIELLEMENT_LIVREE", "Partiellement livrée"
    RETOURNEE = "RETOURNEE", "Retournée"


class BonLivraison(ValidationAvantEnregistrement, models.Model):
    """
    Étape 2 du circuit (§12.3, points 10-13) : le BL est généré après
    la sortie magasin, le chauffeur livre, le client signe, et le
    Responsable Distribution confirme la livraison finale.
    """
    numero = models.CharField("Numéro BL", max_length=30, unique=True, editable=False)
    commande = models.OneToOneField(Commande, verbose_name="Commande", on_delete=models.PROTECT, related_name="bon_livraison")
    tournee = models.ForeignKey(Tournee, verbose_name="Tournée", on_delete=models.SET_NULL, null=True, blank=True)
    statut = models.CharField("Statut", max_length=25, choices=StatutLivraison.choices, default=StatutLivraison.EN_LIVRAISON)
    signature_client = models.BooleanField("Signé par le client", default=False)
    confirme_par = models.ForeignKey(
        Utilisateur, verbose_name="Livraison confirmée par (Resp. Distribution)",
        on_delete=models.PROTECT, null=True, blank=True,
        related_name="livraisons_confirmees",
    )
    date_generation = models.DateTimeField("Date de génération", auto_now_add=True)
    date_livraison = models.DateTimeField("Date de livraison", null=True, blank=True)

    class Meta:
        verbose_name = "Bon de livraison"
        verbose_name_plural = "Bons de livraison"
        ordering = ["-date_generation"]

    def __str__(self):
        return f"{self.numero} - {self.commande.numero}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("BL")
        super().save(*args, **kwargs)

    def clean(self):
        """
        - un BL n'est généré qu'APRÈS la sortie magasin de la commande (§12.3) ;
        - la commande ne change plus ; un BL livré est figé (il sert de
          base aux réclamations) ;
        - le passage à « Livrée » se fait uniquement par la confirmation
          du Responsable Distribution (action /confirmer_livraison/).
        """
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutLivraison.LIVREE:
            raise ValidationError(f"Le bon de livraison {self.numero} est déjà livré : il ne peut plus être modifié.")
        if ancien_statut is None and self.statut != StatutLivraison.EN_LIVRAISON:
            raise ValidationError({"statut": "Un bon de livraison est toujours créé « En livraison »."})
        if self.pk and valeur_en_base(self, "commande") != self.commande_id:
            raise ValidationError({"commande": "La commande d'un bon de livraison ne peut pas être changée."})
        if ancien_statut is None and self.commande_id:
            preparation = PreparationLivraison.objects.filter(commande_id=self.commande_id).first()
            if preparation is None or preparation.statut != StatutPreparation.SORTIE_MAGASIN:
                raise ValidationError({"commande": (
                    f"La commande {self.commande.numero} n'est pas encore sortie du magasin : "
                    "le bon de livraison ne peut pas être généré."
                )})

    def verifier_suppression(self):
        if self.statut == StatutLivraison.LIVREE or self.reclamations.exists():
            raise ValidationError("Un bon de livraison livré ou faisant l'objet d'une réclamation ne peut pas être supprimé.")


class TransfertDepot(ValidationAvantEnregistrement, models.Model):
    """Transfert d'un article entre deux dépôts."""
    depot_source = models.ForeignKey(Depot, verbose_name="Dépôt source", on_delete=models.PROTECT, related_name="transferts_sortants")
    depot_destination = models.ForeignKey(Depot, verbose_name="Dépôt destination", on_delete=models.PROTECT, related_name="transferts_entrants")
    date_transfert = models.DateTimeField("Date de transfert", auto_now_add=True)
    statut = models.CharField("Statut", max_length=20, default="EN_COURS")

    class Meta:
        verbose_name = "Transfert entre dépôts"
        verbose_name_plural = "Transferts entre dépôts"

    def __str__(self):
        return f"Transfert {self.depot_source} -> {self.depot_destination}"

    def clean(self):
        if self.depot_source_id and self.depot_source_id == self.depot_destination_id:
            raise ValidationError({"depot_destination": "Le dépôt de destination doit être différent du dépôt source."})
