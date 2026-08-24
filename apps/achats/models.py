"""
Module 3 - Achats et approvisionnements.

Couvre tous les onglets prévus au §6.1 du cahier des charges :
besoins d'approvisionnement, demandes d'achat, commandes fournisseurs,
fournisseurs, réceptions, contrôle réception, retours fournisseurs.

Piloté par le profil RESPONSABLE_ACHATS (ajouté car le cahier des
charges décrit ce module en détail sans jamais nommer explicitement
qui le pilote - voir échange avec le client à ce sujet). Le
Responsable Achat gère :
- les fournisseurs et leurs contrats (ContratFournisseur)
- le catalogue des produits que chaque fournisseur peut livrer, avec
  son prix (ArticleFournisseur)
- les commandes fournisseurs et leur suivi jusqu'à réception
"""

from django.db import models
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero


class Fournisseur(models.Model):
    """Un fournisseur de matières premières, emballages ou services."""
    code = models.CharField("Code fournisseur", max_length=30, unique=True)
    nom = models.CharField("Nom", max_length=150)
    contact = models.CharField("Contact", max_length=150, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    email = models.EmailField("Email", blank=True)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    gere_par = models.ForeignKey(
        Utilisateur, verbose_name="Géré par (Responsable Achat)",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fournisseurs_geres",
    )
    actif = models.BooleanField("Actif", default=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.code} - {self.nom}"


class StatutContratFournisseur(models.TextChoices):
    ACTIF = "ACTIF", "Actif"
    EXPIRE = "EXPIRE", "Expiré"
    RESILIE = "RESILIE", "Résilié"
    BROUILLON = "BROUILLON", "Brouillon"


class ContratFournisseur(models.Model):
    """
    Le contrat qui lie EVAM à un fournisseur : conditions générales,
    durée, éventuellement des prix ou délais négociés qui s'appliquent
    par défaut aux ArticleFournisseur de ce fournisseur.
    Géré exclusivement par le Responsable Achat.
    """
    numero = models.CharField("Numéro de contrat", max_length=30, unique=True, editable=False)
    fournisseur = models.ForeignKey(
        Fournisseur, verbose_name="Fournisseur", on_delete=models.CASCADE,
        related_name="contrats",
    )
    date_debut = models.DateField("Date de début")
    date_fin = models.DateField("Date de fin", null=True, blank=True)
    conditions = models.TextField(
        "Conditions particulières", blank=True,
        help_text="Modalités de paiement, délais de livraison garantis, pénalités, exclusivité...",
    )
    statut = models.CharField(
        "Statut", max_length=15, choices=StatutContratFournisseur.choices,
        default=StatutContratFournisseur.BROUILLON,
    )
    gere_par = models.ForeignKey(
        Utilisateur, verbose_name="Négocié par (Responsable Achat)",
        on_delete=models.PROTECT, related_name="contrats_fournisseurs_geres",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Contrat fournisseur"
        verbose_name_plural = "Contrats fournisseurs"
        ordering = ["-date_debut"]

    def __str__(self):
        return f"{self.numero} - {self.fournisseur.nom} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("CTF")
        super().save(*args, **kwargs)


class ArticleFournisseur(models.Model):
    """
    Le catalogue : quel fournisseur peut livrer quel article, à quel
    prix et sous quel délai. C'est cette table que le Responsable
    Achat consulte pour choisir un fournisseur au moment de créer une
    commande ("achats des produits fournis par les fournisseurs").
    """
    fournisseur = models.ForeignKey(
        Fournisseur, verbose_name="Fournisseur", on_delete=models.CASCADE,
        related_name="articles_fournis",
    )
    article = models.ForeignKey(
        Article, verbose_name="Article fourni", on_delete=models.CASCADE,
        related_name="fournisseurs_disponibles",
    )
    contrat = models.ForeignKey(
        ContratFournisseur, verbose_name="Contrat associé", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="articles_couverts",
    )
    prix_unitaire = models.DecimalField("Prix unitaire négocié", max_digits=14, decimal_places=2)
    delai_livraison_jours = models.PositiveIntegerField("Délai de livraison (jours)", null=True, blank=True)
    reference_fournisseur = models.CharField("Référence chez le fournisseur", max_length=100, blank=True)

    class Meta:
        verbose_name = "Article fourni par un fournisseur"
        verbose_name_plural = "Catalogue des articles fournisseurs"
        unique_together = ("fournisseur", "article")

    def __str__(self):
        return f"{self.article.code} chez {self.fournisseur.nom} : {self.prix_unitaire}"


class OrigineBesoin(models.TextChoices):
    AUTO_PRODUCTION = "AUTO_PRODUCTION", "Généré automatiquement par la production"
    MANUEL = "MANUEL", "Saisi manuellement"


class BesoinApprovisionnement(models.Model):
    """
    Un besoin d'achat. Le cahier des charges (§6.2) précise que ce
    besoin peut être généré automatiquement quand un stock passe sous
    un seuil suite à un OF, ou saisi manuellement par le service achats.
    """
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    quantite_besoin = models.DecimalField("Quantité nécessaire", max_digits=14, decimal_places=3)
    origine = models.CharField("Origine du besoin", max_length=20, choices=OrigineBesoin.choices)
    satisfait = models.BooleanField("Satisfait par une commande", default=False)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Besoin d'approvisionnement"
        verbose_name_plural = "Besoins d'approvisionnement"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Besoin {self.quantite_besoin} {self.article.code}"


class StatutDemandeAchat(models.TextChoices):
    """Onglet "demandes d'achat" du §6.1 - distinct de la commande :
    une demande interne à valider avant de devenir une commande fournisseur."""
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    APPROUVEE = "APPROUVEE", "Approuvée"
    REJETEE = "REJETEE", "Rejetée"
    TRANSFORMEE = "TRANSFORMEE", "Transformée en commande"


class DemandeAchat(models.Model):
    """
    Une demande d'achat interne (ex : émise par le Responsable
    Production ou issue d'un BesoinApprovisionnement), que le
    Responsable Achat approuve avant de créer la commande fournisseur
    correspondante.
    """
    besoin = models.ForeignKey(
        BesoinApprovisionnement, verbose_name="Besoin d'origine",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="demandes_achat",
    )
    article = models.ForeignKey(Article, verbose_name="Article demandé", on_delete=models.PROTECT)
    quantite_demandee = models.DecimalField("Quantité demandée", max_digits=14, decimal_places=3)
    motif = models.TextField("Motif", blank=True)
    demandeur = models.ForeignKey(
        Utilisateur, verbose_name="Demandeur", on_delete=models.PROTECT,
        related_name="demandes_achat_emises",
    )
    statut = models.CharField(
        "Statut", max_length=15, choices=StatutDemandeAchat.choices,
        default=StatutDemandeAchat.EN_ATTENTE,
    )
    approuve_par = models.ForeignKey(
        Utilisateur, verbose_name="Approuvée par (Responsable Achat)",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="demandes_achat_approuvees",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    date_traitement = models.DateTimeField("Date de traitement", null=True, blank=True)

    class Meta:
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Demande {self.quantite_demandee} {self.article.code} ({self.get_statut_display()})"

    def approuver(self, utilisateur):
        from django.utils import timezone
        self.statut = StatutDemandeAchat.APPROUVEE
        self.approuve_par = utilisateur
        self.date_traitement = timezone.now()
        self.save()

    def rejeter(self, utilisateur):
        from django.utils import timezone
        self.statut = StatutDemandeAchat.REJETEE
        self.approuve_par = utilisateur
        self.date_traitement = timezone.now()
        self.save()


class StatutCommandeFournisseur(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    ENVOYEE = "ENVOYEE", "Envoyée"
    PARTIELLEMENT_RECUE = "PARTIELLEMENT_RECUE", "Partiellement reçue"
    RECUE = "RECUE", "Reçue"
    ANNULEE = "ANNULEE", "Annulée"


class CommandeFournisseur(models.Model):
    """La commande passée par le Responsable Achat à un fournisseur."""
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    fournisseur = models.ForeignKey(Fournisseur, verbose_name="Fournisseur", on_delete=models.PROTECT, related_name="commandes")
    demande_achat = models.ForeignKey(
        DemandeAchat, verbose_name="Demande d'achat d'origine",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="commandes",
    )
    statut = models.CharField(
        "Statut", max_length=25, choices=StatutCommandeFournisseur.choices,
        default=StatutCommandeFournisseur.BROUILLON,
    )
    cree_par = models.ForeignKey(
        Utilisateur, verbose_name="Créée par (Responsable Achat)",
        on_delete=models.PROTECT, related_name="commandes_fournisseurs_creees",
    )
    date_commande = models.DateTimeField("Date de commande", auto_now_add=True)

    class Meta:
        verbose_name = "Commande fournisseur"
        verbose_name_plural = "Commandes fournisseurs"
        ordering = ["-date_commande"]

    def __str__(self):
        return f"{self.numero} - {self.fournisseur.nom}"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("CMF")
        super().save(*args, **kwargs)

    @property
    def montant_total(self):
        return sum((l.quantite_commandee * l.prix_unitaire for l in self.lignes.all()), start=0)

    def envoyer(self):
        if self.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValueError("Seule une commande en brouillon peut être envoyée.")
        self.statut = StatutCommandeFournisseur.ENVOYEE
        self.save()


class LigneCommandeFournisseur(models.Model):
    commande = models.ForeignKey(
        CommandeFournisseur, verbose_name="Commande", on_delete=models.CASCADE,
        related_name="lignes",
    )
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    quantite_commandee = models.DecimalField("Quantité commandée", max_digits=14, decimal_places=3)
    prix_unitaire = models.DecimalField("Prix unitaire", max_digits=14, decimal_places=2)
    quantite_recue = models.DecimalField("Quantité reçue", max_digits=14, decimal_places=3, default=0)

    class Meta:
        verbose_name = "Ligne de commande fournisseur"
        verbose_name_plural = "Lignes de commande fournisseur"

    def __str__(self):
        return f"{self.commande.numero} : {self.quantite_commandee} {self.article.code}"

    @property
    def montant_ligne(self):
        return self.quantite_commandee * self.prix_unitaire


class ReceptionAchat(models.Model):
    """
    Réception physique d'une commande fournisseur (déclenche un
    mouvement d'ENTREE en stock, voir apps/achats/views.py). Inclut le
    contrôle réception (onglet §6.1) : conformité constatée par le
    Magasinier ou le Responsable Achat à l'arrivée de la marchandise.
    """
    commande = models.ForeignKey(
        CommandeFournisseur, verbose_name="Commande", on_delete=models.PROTECT,
        related_name="receptions",
    )
    receptionne_par = models.ForeignKey(Utilisateur, verbose_name="Réceptionné par", on_delete=models.PROTECT)
    conforme = models.BooleanField(
        "Réception conforme", default=True,
        help_text="Contrôle réception : la livraison correspond-elle à la commande ?",
    )
    observations = models.TextField("Observations", blank=True)
    date_reception = models.DateTimeField("Date de réception", auto_now_add=True)

    class Meta:
        verbose_name = "Réception d'achat"
        verbose_name_plural = "Réceptions d'achats"
        ordering = ["-date_reception"]

    def __str__(self):
        return f"Réception {self.commande.numero} du {self.date_reception:%Y-%m-%d}"


class LigneReceptionAchat(models.Model):
    """Détail par article reçu, pour mettre à jour quantite_recue de la ligne de commande correspondante."""
    reception = models.ForeignKey(
        ReceptionAchat, verbose_name="Réception", on_delete=models.CASCADE,
        related_name="lignes",
    )
    ligne_commande = models.ForeignKey(
        LigneCommandeFournisseur, verbose_name="Ligne de commande", on_delete=models.PROTECT,
        related_name="lignes_reception",
    )
    quantite_recue = models.DecimalField("Quantité reçue", max_digits=14, decimal_places=3)

    class Meta:
        verbose_name = "Ligne de réception"
        verbose_name_plural = "Lignes de réception"

    def __str__(self):
        return f"{self.reception} : {self.quantite_recue} {self.ligne_commande.article.code}"


class MotifRetourFournisseur(models.TextChoices):
    NON_CONFORME = "NON_CONFORME", "Non conforme"
    ENDOMMAGE = "ENDOMMAGE", "Endommagé au transport"
    QUANTITE_EXCEDENTAIRE = "QUANTITE_EXCEDENTAIRE", "Quantité excédentaire livrée"
    ERREUR_REFERENCE = "ERREUR_REFERENCE", "Erreur de référence"
    AUTRE = "AUTRE", "Autre"


class RetourFournisseur(models.Model):
    """Onglet "retours fournisseurs" du §6.1 : marchandise reçue puis retournée au fournisseur."""
    reception = models.ForeignKey(
        ReceptionAchat, verbose_name="Réception concernée", on_delete=models.PROTECT,
        related_name="retours",
    )
    article = models.ForeignKey(Article, verbose_name="Article retourné", on_delete=models.PROTECT)
    quantite_retournee = models.DecimalField("Quantité retournée", max_digits=14, decimal_places=3)
    motif = models.CharField("Motif", max_length=25, choices=MotifRetourFournisseur.choices)
    observations = models.TextField("Observations", blank=True)
    traite_par = models.ForeignKey(Utilisateur, verbose_name="Traité par", on_delete=models.PROTECT)
    date_retour = models.DateTimeField("Date de retour", auto_now_add=True)

    class Meta:
        verbose_name = "Retour fournisseur"
        verbose_name_plural = "Retours fournisseurs"
        ordering = ["-date_retour"]

    def __str__(self):
        return f"Retour {self.quantite_retournee} {self.article.code} - {self.get_motif_display()}"
