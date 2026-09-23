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

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_ordre_dates,
    valeur_en_base, verifier_transition,
)


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


class ContratFournisseur(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        exiger_ordre_dates(self.date_debut, self.date_fin, "date_fin", "la date de début", "La date de fin")


class ArticleFournisseur(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire négocié")
        if self.contrat_id and self.fournisseur_id and self.contrat.fournisseur_id != self.fournisseur_id:
            raise ValidationError({"contrat": "Ce contrat appartient à un autre fournisseur."})


class OrigineBesoin(models.TextChoices):
    AUTO_PRODUCTION = "AUTO_PRODUCTION", "Généré automatiquement par la production"
    MANUEL = "MANUEL", "Saisi manuellement"


class BesoinApprovisionnement(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        exiger_positif(self.quantite_besoin, "quantite_besoin", "La quantité nécessaire")


class StatutDemandeAchat(models.TextChoices):
    """Onglet "demandes d'achat" du §6.1 - distinct de la commande :
    une demande interne à valider avant de devenir une commande fournisseur."""
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    APPROUVEE = "APPROUVEE", "Approuvée"
    REJETEE = "REJETEE", "Rejetée"
    TRANSFORMEE = "TRANSFORMEE", "Transformée en commande"


class DemandeAchat(ValidationAvantEnregistrement, models.Model):
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

    TRANSITIONS = {
        StatutDemandeAchat.EN_ATTENTE: {StatutDemandeAchat.APPROUVEE, StatutDemandeAchat.REJETEE},
        StatutDemandeAchat.APPROUVEE: {StatutDemandeAchat.TRANSFORMEE},
    }

    def clean(self):
        exiger_positif(self.quantite_demandee, "quantite_demandee", "La quantité demandée")
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutDemandeAchat.REJETEE, StatutDemandeAchat.TRANSFORMEE):
            raise ValidationError(
                f"Cette demande est {dict(StatutDemandeAchat.choices)[ancien_statut].lower()} : elle ne peut plus être modifiée."
            )
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de la demande",
            initial=StatutDemandeAchat.EN_ATTENTE,
        )
        if ancien_statut == StatutDemandeAchat.APPROUVEE:
            for champ in ("article",):
                if valeur_en_base(self, champ) != self.article_id:
                    raise ValidationError({champ: "Une demande approuvée ne peut plus changer d'article."})
            if valeur_en_base(self, "quantite_demandee") != self.quantite_demandee:
                raise ValidationError({"quantite_demandee": "Une demande approuvée ne peut plus changer de quantité."})

    def verifier_suppression(self):
        if self.statut != StatutDemandeAchat.EN_ATTENTE:
            raise ValidationError("Seule une demande en attente peut être supprimée.")

    def _verifier_en_attente(self):
        if self.statut != StatutDemandeAchat.EN_ATTENTE:
            raise ValueError(f"Cette demande est déjà {self.get_statut_display().lower()}.")

    def approuver(self, utilisateur):
        from django.utils import timezone
        self._verifier_en_attente()
        self.statut = StatutDemandeAchat.APPROUVEE
        self.approuve_par = utilisateur
        self.date_traitement = timezone.now()
        self.save()

    def rejeter(self, utilisateur):
        from django.utils import timezone
        self._verifier_en_attente()
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


class CommandeFournisseur(ValidationAvantEnregistrement, models.Model):
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

    TRANSITIONS = {
        StatutCommandeFournisseur.BROUILLON: {StatutCommandeFournisseur.ENVOYEE, StatutCommandeFournisseur.ANNULEE},
        StatutCommandeFournisseur.ENVOYEE: {
            StatutCommandeFournisseur.PARTIELLEMENT_RECUE, StatutCommandeFournisseur.RECUE,
            StatutCommandeFournisseur.ANNULEE,
        },
        StatutCommandeFournisseur.PARTIELLEMENT_RECUE: {StatutCommandeFournisseur.RECUE},
    }

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.numero:
                self.numero = generer_numero("CMF")
            nouvelle = self._state.adding
            super().save(*args, **kwargs)
            # La demande d'achat approuvée devient "Transformée en commande".
            if nouvelle and self.demande_achat_id:
                self.demande_achat.statut = StatutDemandeAchat.TRANSFORMEE
                self.demande_achat.save()

    def clean(self):
        """
        - fournisseur actif, demande d'achat d'origine approuvée ;
        - statut : Brouillon -> Envoyée -> (Partiellement) reçue, ou
          Annulée tant que rien n'a été reçu ; Reçue/Annulée sont figées ;
        - fournisseur et demande ne changent plus après le brouillon.
        """
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutCommandeFournisseur.RECUE, StatutCommandeFournisseur.ANNULEE):
            raise ValidationError(
                f"La commande {self.numero} est {dict(StatutCommandeFournisseur.choices)[ancien_statut].lower()} : "
                "elle ne peut plus être modifiée."
            )
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de la commande fournisseur",
            initial=StatutCommandeFournisseur.BROUILLON,
        )
        if self.statut == StatutCommandeFournisseur.ANNULEE and self.pk and self.receptions.exists():
            raise ValidationError({"statut": "Cette commande a déjà des réceptions : elle ne peut plus être annulée."})
        if ancien_statut is None:
            if self.fournisseur_id and not self.fournisseur.actif:
                raise ValidationError({"fournisseur": f"Le fournisseur « {self.fournisseur.nom} » est inactif."})
            if self.demande_achat_id and self.demande_achat.statut != StatutDemandeAchat.APPROUVEE:
                raise ValidationError({"demande_achat": (
                    f"La demande d'achat est {self.demande_achat.get_statut_display().lower()} : "
                    "seule une demande approuvée peut devenir une commande."
                )})
        elif ancien_statut != StatutCommandeFournisseur.BROUILLON:
            if valeur_en_base(self, "fournisseur") != self.fournisseur_id:
                raise ValidationError({"fournisseur": "Le fournisseur ne peut plus être changé après l'envoi."})
        if self.pk and valeur_en_base(self, "demande_achat") != self.demande_achat_id:
            raise ValidationError({"demande_achat": "La demande d'achat d'origine ne peut pas être changée."})

    def verifier_suppression(self):
        if self.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValidationError("Seule une commande fournisseur en brouillon peut être supprimée ; sinon, annulez-la.")

    @property
    def montant_total(self):
        return sum((l.quantite_commandee * l.prix_unitaire for l in self.lignes.all()), start=0)

    def envoyer(self):
        if self.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValueError("Seule une commande en brouillon peut être envoyée.")
        if not self.lignes.exists():
            raise ValueError("Impossible d'envoyer une commande sans aucune ligne.")
        self.statut = StatutCommandeFournisseur.ENVOYEE
        self.save()


class LigneCommandeFournisseur(ValidationAvantEnregistrement, models.Model):
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

    @property
    def reste_a_recevoir(self):
        return self.quantite_commandee - self.quantite_recue

    def clean(self):
        """Les lignes ne se saisissent/modifient que tant que la commande est en brouillon."""
        exiger_positif(self.quantite_commandee, "quantite_commandee", "La quantité commandée")
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire")
        if self.pk:
            ancienne = CommandeFournisseur.objects.filter(pk=valeur_en_base(self, "commande")).first()
            if ancienne and ancienne.statut != StatutCommandeFournisseur.BROUILLON:
                # Seule la mise à jour de quantite_recue par une réception est permise.
                if (valeur_en_base(self, "commande") != self.commande_id
                        or valeur_en_base(self, "article") != self.article_id
                        or valeur_en_base(self, "quantite_commandee") != self.quantite_commandee
                        or valeur_en_base(self, "prix_unitaire") != self.prix_unitaire):
                    raise ValidationError(
                        f"La commande {ancienne.numero} a été envoyée : ses lignes ne peuvent plus être modifiées."
                    )
        elif self.commande_id and self.commande.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValidationError({"commande": (
                f"La commande {self.commande.numero} a été envoyée : on ne peut plus y ajouter de ligne."
            )})
        if self.quantite_recue is not None and self.quantite_commandee is not None \
                and self.quantite_recue > self.quantite_commandee:
            raise ValidationError({"quantite_recue": "La quantité reçue dépasse la quantité commandée."})

    def verifier_suppression(self):
        if self.commande.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValidationError("La commande a été envoyée : ses lignes ne peuvent plus être supprimées.")


class ReceptionAchat(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        if self.pk and valeur_en_base(self, "commande") != self.commande_id:
            raise ValidationError({"commande": "La commande d'une réception ne peut pas être changée."})
        if self.pk is None and self.commande_id and self.commande.statut not in (
            StatutCommandeFournisseur.ENVOYEE, StatutCommandeFournisseur.PARTIELLEMENT_RECUE,
        ):
            raise ValidationError({"commande": (
                f"La commande {self.commande.numero} est {self.commande.get_statut_display().lower()} : "
                "seule une commande envoyée (ou partiellement reçue) peut être réceptionnée."
            )})

    def verifier_suppression(self):
        if self.lignes.exists() or self.retours.exists():
            raise ValidationError("Cette réception a déjà des lignes (stock mouvementé) : elle ne peut pas être supprimée.")


class LigneReceptionAchat(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        """
        - une ligne de réception ne se modifie pas (le stock est déjà entré) ;
        - quantité strictement positive, au plus le reste à recevoir ;
        - la ligne de commande doit appartenir à la commande réceptionnée.
        """
        if self.pk is not None:
            raise ValidationError("Une ligne de réception enregistrée ne peut pas être modifiée.")
        exiger_positif(self.quantite_recue, "quantite_recue", "La quantité reçue")
        if self.reception_id and self.ligne_commande_id:
            if self.ligne_commande.commande_id != self.reception.commande_id:
                raise ValidationError({"ligne_commande": (
                    "Cette ligne n'appartient pas à la commande de la réception "
                    f"({self.reception.commande.numero})."
                )})
            if self.reception.commande.statut not in (
                StatutCommandeFournisseur.ENVOYEE, StatutCommandeFournisseur.PARTIELLEMENT_RECUE,
            ):
                raise ValidationError({"reception": "La commande de cette réception n'est plus en attente de livraison."})
            reste = self.ligne_commande.reste_a_recevoir
            if self.quantite_recue > reste:
                raise ValidationError({"quantite_recue": (
                    f"Quantité reçue ({self.quantite_recue}) supérieure au reste à recevoir ({reste}) "
                    f"pour {self.ligne_commande.article.code}."
                )})

    def verifier_suppression(self):
        raise ValidationError("Une ligne de réception ne peut pas être supprimée (le stock a déjà été mouvementé).")

    def save(self, *args, **kwargs):
        """
        Enregistre la ligne ET ses conséquences (quantité reçue de la
        ligne de commande, statut de la commande, entrée en stock) en
        une seule transaction : tout ou rien.
        """
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        with transaction.atomic():
            creation = self._state.adding
            super().save(*args, **kwargs)
            if not creation:
                return
            ligne_commande = LigneCommandeFournisseur.objects.select_for_update().get(pk=self.ligne_commande_id)
            ligne_commande.quantite_recue += self.quantite_recue
            ligne_commande.save()

            commande = ligne_commande.commande
            totaux = commande.lignes.aggregate(commande=Sum("quantite_commandee"), recu=Sum("quantite_recue"))
            commande.statut = (
                StatutCommandeFournisseur.RECUE if totaux["recu"] >= totaux["commande"]
                else StatutCommandeFournisseur.PARTIELLEMENT_RECUE
            )
            commande.save()

            MouvementStock.objects.create(
                article=ligne_commande.article,
                depot=depot_par_defaut("Magasin principal"),
                type_mouvement=TypeMouvement.ENTREE,
                quantite=self.quantite_recue,
                motif=f"Réception achat {self.reception_id} - commande {commande.numero}",
                document_origine=commande.numero,
                utilisateur=self.reception.receptionne_par,
            )


class MotifRetourFournisseur(models.TextChoices):
    NON_CONFORME = "NON_CONFORME", "Non conforme"
    ENDOMMAGE = "ENDOMMAGE", "Endommagé au transport"
    QUANTITE_EXCEDENTAIRE = "QUANTITE_EXCEDENTAIRE", "Quantité excédentaire livrée"
    ERREUR_REFERENCE = "ERREUR_REFERENCE", "Erreur de référence"
    AUTRE = "AUTRE", "Autre"


class RetourFournisseur(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        """
        On ne retourne que ce qui a été reçu dans CETTE réception, moins
        ce qui a déjà été retourné.
        """
        if self.pk is not None:
            raise ValidationError("Un retour fournisseur enregistré ne peut pas être modifié.")
        exiger_positif(self.quantite_retournee, "quantite_retournee", "La quantité retournée")
        if self.reception_id and self.article_id:
            recu = self.reception.lignes.filter(
                ligne_commande__article_id=self.article_id,
            ).aggregate(total=Sum("quantite_recue"))["total"] or 0
            if recu == 0:
                raise ValidationError({"article": f"L'article {self.article.code} n'a pas été reçu dans cette réception."})
            deja_retourne = RetourFournisseur.objects.filter(
                reception_id=self.reception_id, article_id=self.article_id,
            ).aggregate(total=Sum("quantite_retournee"))["total"] or 0
            retournable = recu - deja_retourne
            if self.quantite_retournee > retournable:
                raise ValidationError({"quantite_retournee": (
                    f"Retour impossible : {retournable} de {self.article.code} au plus peut encore être retourné "
                    f"(reçu {recu}, déjà retourné {deja_retourne})."
                )})

    def verifier_suppression(self):
        raise ValidationError("Un retour fournisseur ne peut pas être supprimé (le stock a déjà été mouvementé).")

    def save(self, *args, **kwargs):
        """La marchandise retournée quitte physiquement le magasin : sortie de stock dans la même transaction."""
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        with transaction.atomic():
            creation = self._state.adding
            super().save(*args, **kwargs)
            if creation:
                MouvementStock.objects.create(
                    article=self.article,
                    depot=depot_par_defaut("Magasin principal"),
                    type_mouvement=TypeMouvement.SORTIE,
                    quantite=self.quantite_retournee,
                    motif=f"Retour fournisseur ({self.get_motif_display()}) - commande {self.reception.commande.numero}",
                    document_origine=self.reception.commande.numero,
                    utilisateur=self.traite_par,
                )
