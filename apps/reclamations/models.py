"""
Retour client / Réclamation.

Reproduit exactement le circuit du croquis "Processus retour client -
EVAM (BL déjà validé)" :

    Réclamation -> Retour physique -> Contrôle -> Décision
        -> Récupérable direct : réintégration stock
        -> Récupérable avec intervention : reconditionnement -> réintégration
        -> Non récupérable : sortie définitive (rebut) + coût de perte
    -> Solution client (remplacement / avoir / remboursement)

Règles clés du croquis, appliquées dans le code :
1. BL validé = livraison clôturée (le circuit démarre APRÈS un BL déjà
   validé, voir apps.distribution.BonLivraison).
2. Toute erreur constatée après création d'une réclamation.
3. Un produit retourné ne revient dans le stock DISPONIBLE qu'après
   contrôle (voir RetourPhysique -> zone de quarantaine, jamais
   directement dans StockArticle.quantite_physique disponible).
4. Chaque opération est liée à : BL -> Facture -> Client -> Produit -> Lot.

Limite connue (voir README) : le croquis prévoit un impact automatique
sur le module Caisse pour les remboursements ("sortie de caisse"), mais
aucun modèle de décaissement distinct de l'encaissement n'existe encore
dans apps.caisse. SolutionClient.montant_rembourse est donc enregistré
ici avec une référence texte, pas une vraie écriture de caisse.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.commercial.models import Client, Facture, Commande
from apps.distribution.models import BonLivraison
from apps.qualite.models import Lot
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_positif_optionnel,
    valeur_en_base, verifier_transition, convertir_decimal,
)


class TypeProbleme(models.TextChoices):
    PRODUIT_DEFECTUEUX = "PRODUIT_DEFECTUEUX", "Produit défectueux"
    PRODUIT_MANQUANT = "PRODUIT_MANQUANT", "Produit manquant"
    ERREUR_REFERENCE = "ERREUR_REFERENCE", "Erreur de référence livrée"
    EMBALLAGE_ENDOMMAGE = "EMBALLAGE_ENDOMMAGE", "Emballage endommagé"
    PRODUIT_PERIME = "PRODUIT_PERIME", "Produit périmé"
    AUTRE = "AUTRE", "Autre"


class StatutReclamation(models.TextChoices):
    OUVERTE = "OUVERTE", "Ouverte"
    EN_COURS = "EN_COURS", "En cours"
    CLOTUREE = "CLOTUREE", "Clôturée"


class ReclamationClient(ValidationAvantEnregistrement, models.Model):
    """
    Point d'entrée du circuit (bloc 6 du croquis). Rattachée à un BL
    déjà validé - "Recherche du BL" - avec les infos client/facture
    reprises automatiquement (règle §15 : pas de ressaisie), pas de
    retour physique obligatoire ("sans retour ou avec retour").
    """
    numero = models.CharField("N° réclamation", max_length=30, unique=True, editable=False)
    bon_livraison = models.ForeignKey(
        BonLivraison, verbose_name="Bon de livraison", on_delete=models.PROTECT,
        null=True, blank=True, related_name="reclamations",
        help_text="Recherche du BL - laisser vide si le BL n'a pas pu être retrouvé.",
    )
    client = models.ForeignKey(Client, verbose_name="Client", on_delete=models.PROTECT, related_name="reclamations")
    facture = models.ForeignKey(
        Facture, verbose_name="Facture", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="reclamations",
    )
    article = models.ForeignKey(Article, verbose_name="Produit concerné", on_delete=models.PROTECT)
    quantite = models.DecimalField("Quantité concernée", max_digits=12, decimal_places=3)
    prix_unitaire = models.DecimalField(
        "Prix unitaire (repris de la facture)", max_digits=14, decimal_places=2,
        null=True, blank=True,
    )
    type_probleme = models.CharField("Type de problème", max_length=30, choices=TypeProbleme.choices)
    description = models.TextField("Description")
    produit_retourne = models.BooleanField(
        "Le client a-t-il ramené le produit ?", default=False,
        help_text="Si oui, un RetourPhysique doit être créé pour cette réclamation.",
    )
    statut = models.CharField("Statut", max_length=15, choices=StatutReclamation.choices, default=StatutReclamation.OUVERTE)
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Créée par", on_delete=models.PROTECT)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    date_cloture = models.DateTimeField("Date de clôture", null=True, blank=True)

    class Meta:
        verbose_name = "Réclamation client"
        verbose_name_plural = "Réclamations clients"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero} - {self.client.nom} ({self.get_statut_display()})"

    TRANSITIONS = {
        StatutReclamation.OUVERTE: {StatutReclamation.EN_COURS, StatutReclamation.CLOTUREE},
        StatutReclamation.EN_COURS: {StatutReclamation.CLOTUREE},
    }

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("RCL")
        super().save(*args, **kwargs)

    def clean(self):
        """
        Règle clé n°4 du circuit : chaque opération est liée à
        BL -> Facture -> Client -> Produit. Les informations saisies
        doivent donc être COHÉRENTES entre elles :
        - le BL doit être livré (le circuit démarre après un BL validé) ;
        - client, facture et produit doivent correspondre au BL/à la commande ;
        - la quantité réclamée ne dépasse pas la quantité livrée.
        Une réclamation clôturée est figée.
        """
        exiger_positif(self.quantite, "quantite", "La quantité concernée")
        exiger_positif_optionnel(self.prix_unitaire, "prix_unitaire", "Le prix unitaire")
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutReclamation.CLOTUREE:
            raise ValidationError(f"La réclamation {self.numero} est clôturée : elle ne peut plus être modifiée.")
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de la réclamation",
            initial=StatutReclamation.OUVERTE,
        )
        if self.pk and (
            RetourPhysique.objects.filter(reclamation_id=self.pk).exists()
            or SolutionClient.objects.filter(reclamation_id=self.pk).exists()
        ):
            for champ in ("bon_livraison", "client", "facture", "article"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Un retour ou une solution existe déjà : ce champ ne peut plus être modifié."})
            if valeur_en_base(self, "quantite") != self.quantite:
                raise ValidationError({"quantite": "Un retour ou une solution existe déjà : la quantité ne peut plus être modifiée."})

        commande = None
        if self.bon_livraison_id:
            bl = self.bon_livraison
            if bl.statut not in ("LIVREE", "PARTIELLEMENT_LIVREE"):
                raise ValidationError({"bon_livraison": (
                    f"Le bon de livraison {bl.numero} n'est pas encore livré : "
                    "une réclamation ne peut porter que sur une livraison validée."
                )})
            commande = bl.commande
        if self.facture_id:
            if commande is not None and self.facture.commande_id != commande.id:
                raise ValidationError({"facture": "Cette facture ne correspond pas à la commande du bon de livraison."})
            commande = commande or self.facture.commande
            if self.client_id and self.facture.client_id != self.client_id:
                raise ValidationError({"facture": "Cette facture appartient à un autre client."})
        if commande is not None:
            if self.client_id and commande.client_id != self.client_id:
                raise ValidationError({"client": f"Le client ne correspond pas à celui de la commande {commande.numero}."})
            if self.article_id:
                lignes = commande.lignes.filter(article_id=self.article_id)
                quantite_livree = lignes.aggregate(total=Sum("quantite"))["total"] or 0
                if quantite_livree == 0:
                    raise ValidationError({"article": f"Ce produit ne figure pas dans la commande {commande.numero}."})
                if self.quantite is not None and self.quantite > quantite_livree:
                    raise ValidationError({"quantite": (
                        f"Quantité réclamée ({self.quantite}) supérieure à la quantité livrée ({quantite_livree})."
                    )})
                if self.prix_unitaire is None:
                    # Règle §15 : pas de ressaisie, le prix est repris de la commande.
                    premiere_ligne = lignes.first()
                    self.prix_unitaire = premiere_ligne.prix_unitaire if premiere_ligne else None

    def verifier_suppression(self):
        if self.statut != StatutReclamation.OUVERTE or hasattr(self, "retour_physique") or hasattr(self, "solution"):
            raise ValidationError("Une réclamation déjà traitée ne peut pas être supprimée.")

    def cloturer(self):
        """Clôture la réclamation (impact automatique §12 : suivi statut côté Livraison)."""
        from django.utils import timezone
        self.statut = StatutReclamation.CLOTUREE
        self.date_cloture = timezone.now()
        self.save()


class StatutRetourPhysique(models.TextChoices):
    EN_QUARANTAINE = "EN_QUARANTAINE", "En quarantaine"
    CONTROLE_EFFECTUE = "CONTROLE_EFFECTUE", "Contrôle effectué"


class RetourPhysique(ValidationAvantEnregistrement, models.Model):
    """
    Bloc 7 du croquis : le produit revient physiquement. Il est mis en
    quarantaine (jamais réintégré directement au stock disponible,
    règle clé n°3 du croquis) en attendant le contrôle.
    """
    reclamation = models.OneToOneField(
        ReclamationClient, verbose_name="Réclamation", on_delete=models.CASCADE,
        related_name="retour_physique",
    )
    lot = models.ForeignKey(
        Lot, verbose_name="Lot d'origine", on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text="Traçabilité par lot (règle clé n°4 du circuit).",
    )
    quantite_retournee = models.DecimalField("Quantité retournée", max_digits=12, decimal_places=3)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutRetourPhysique.choices,
        default=StatutRetourPhysique.EN_QUARANTAINE,
    )
    receptionne_par = models.ForeignKey(Utilisateur, verbose_name="Réceptionné par", on_delete=models.PROTECT)
    date_reception = models.DateTimeField("Date de réception", auto_now_add=True)

    class Meta:
        verbose_name = "Retour physique"
        verbose_name_plural = "Retours physiques"

    def __str__(self):
        return f"Retour {self.reclamation.numero} ({self.get_statut_display()})"

    def clean(self):
        """
        - quantité retournée strictement positive, au plus la quantité réclamée ;
        - pas de retour sur une réclamation clôturée ;
        - le lot indiqué doit être un lot du produit réclamé ;
        - une fois enregistré (stock en quarantaine), seul le statut
          évolue (par le contrôle).
        """
        exiger_positif(self.quantite_retournee, "quantite_retournee", "La quantité retournée")
        if self.pk:
            for champ in ("reclamation", "lot"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Un retour enregistré ne peut plus être modifié."})
            if valeur_en_base(self, "quantite_retournee") != self.quantite_retournee:
                raise ValidationError({"quantite_retournee": "Un retour enregistré ne peut plus être modifié (stock déjà en quarantaine)."})
            return
        if self.statut != StatutRetourPhysique.EN_QUARANTAINE:
            raise ValidationError({"statut": "Un retour physique est toujours créé « En quarantaine »."})
        if self.reclamation_id:
            reclamation = self.reclamation
            if reclamation.statut == StatutReclamation.CLOTUREE:
                raise ValidationError({"reclamation": f"La réclamation {reclamation.numero} est clôturée."})
            if self.quantite_retournee > reclamation.quantite:
                raise ValidationError({"quantite_retournee": (
                    f"Quantité retournée ({self.quantite_retournee}) supérieure à la quantité "
                    f"réclamée ({reclamation.quantite})."
                )})
            if self.lot_id and self.lot.article_id != reclamation.article_id:
                raise ValidationError({"lot": "Ce lot ne correspond pas au produit réclamé."})

    def verifier_suppression(self):
        raise ValidationError("Un retour physique ne peut pas être supprimé (le stock a déjà été mouvementé).")

    def save(self, *args, **kwargs):
        """À la création, enregistre l'entrée en quarantaine comme un mouvement de stock (impact automatique §12 : Stock)."""
        creation = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creation:
                self._entree_en_quarantaine()
                if not self.reclamation.produit_retourne:
                    self.reclamation.produit_retourne = True
                    self.reclamation.save(update_fields=["produit_retourne"])

    def _entree_en_quarantaine(self):
        from apps.stocks.models import Depot, MouvementStock
        depot_quarantaine, _ = Depot.objects.get_or_create(
            nom="Quarantaine", defaults={"adresse": "Zone de quarantaine - retours clients"},
        )
        MouvementStock.objects.create(
            article=self.reclamation.article, depot=depot_quarantaine,
            type_mouvement="ENTREE", quantite=self.quantite_retournee,
            motif="Retour client en attente de contrôle",
            document_origine=self.reclamation.numero,
            utilisateur=self.receptionne_par,
        )


class ResultatControle(models.TextChoices):
    RECUPERABLE_DIRECT = "RECUPERABLE_DIRECT", "Récupérable directement"
    RECUPERABLE_AVEC_INTERVENTION = "RECUPERABLE_AVEC_INTERVENTION", "Récupérable avec intervention"
    NON_RECUPERABLE = "NON_RECUPERABLE", "Non récupérable"


class ControleRetour(ValidationAvantEnregistrement, models.Model):
    """
    Bloc 8 du croquis : vérification état produit / lot / DLC / qualité,
    puis décision. La décision orchestre automatiquement la suite du
    circuit (blocs 8A/8B/8C) - voir decider().
    """
    retour_physique = models.OneToOneField(
        RetourPhysique, verbose_name="Retour physique", on_delete=models.CASCADE,
        related_name="controle",
    )
    resultat = models.CharField("Résultat", max_length=30, choices=ResultatControle.choices)
    observations = models.TextField("Observations", blank=True)
    controle_par = models.ForeignKey(Utilisateur, verbose_name="Contrôlé par", on_delete=models.PROTECT)
    date_controle = models.DateTimeField("Date de contrôle", auto_now_add=True)

    class Meta:
        verbose_name = "Contrôle de retour"
        verbose_name_plural = "Contrôles de retours"

    def __str__(self):
        return f"Contrôle {self.retour_physique.reclamation.numero} - {self.get_resultat_display()}"

    def clean(self):
        """
        Un contrôle ne se fait qu'une fois, sur un retour encore en
        quarantaine, et ne se modifie plus : sa décision a déjà mouvementé
        le stock (réintégration / rebut) ou lancé un reconditionnement.
        """
        if self.pk is not None:
            raise ValidationError("Un contrôle de retour enregistré ne peut pas être modifié (sa décision a déjà été appliquée).")
        if self.retour_physique_id:
            retour = self.retour_physique
            if retour.statut != StatutRetourPhysique.EN_QUARANTAINE:
                raise ValidationError({"retour_physique": "Ce retour a déjà été contrôlé."})
            if retour.reclamation.statut == StatutReclamation.CLOTUREE:
                raise ValidationError({"retour_physique": "La réclamation de ce retour est clôturée."})

    def verifier_suppression(self):
        raise ValidationError("Un contrôle de retour ne peut pas être supprimé (sa décision a déjà été appliquée).")

    def save(self, *args, **kwargs):
        creation = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.retour_physique.statut = StatutRetourPhysique.CONTROLE_EFFECTUE
            self.retour_physique.save()
            if creation:
                self.decider()

    def decider(self):
        """
        Applique automatiquement la conséquence de la décision
        (§8A/8B/8C du croquis) : réintégration directe, création d'un
        reconditionnement à faire, ou sortie définitive + coût de perte.
        """
        if self.resultat == ResultatControle.RECUPERABLE_DIRECT:
            self._reintegrer_stock(self.retour_physique.quantite_retournee)
        elif self.resultat == ResultatControle.RECUPERABLE_AVEC_INTERVENTION:
            Reconditionnement.objects.get_or_create(controle_retour=self)
        elif self.resultat == ResultatControle.NON_RECUPERABLE:
            self._sortie_definitive()

    def _reintegrer_stock(self, quantite):
        """§8A : sort de la quarantaine, entre dans le stock disponible normal."""
        from apps.stocks.models import Depot, MouvementStock
        depot_quarantaine, _ = Depot.objects.get_or_create(nom="Quarantaine")
        depot_principal, _ = Depot.objects.get_or_create(nom="Magasin principal")
        article = self.retour_physique.reclamation.article

        MouvementStock.objects.create(
            article=article, depot=depot_quarantaine, type_mouvement="SORTIE",
            quantite=quantite, motif="Réintégration après contrôle - récupérable",
            document_origine=self.retour_physique.reclamation.numero,
            utilisateur=self.controle_par,
        )
        MouvementStock.objects.create(
            article=article, depot=depot_principal, type_mouvement="ENTREE",
            quantite=quantite, motif="Réintégration après contrôle - récupérable",
            document_origine=self.retour_physique.reclamation.numero,
            utilisateur=self.controle_par,
        )

    def _sortie_definitive(self):
        """§8C : sortie définitive de la quarantaine (rebut/destruction) + enregistrement du coût perdu."""
        from apps.stocks.models import Depot, MouvementStock
        depot_quarantaine, _ = Depot.objects.get_or_create(nom="Quarantaine")
        MouvementStock.objects.create(
            article=self.retour_physique.reclamation.article, depot=depot_quarantaine,
            type_mouvement="SORTIE", quantite=self.retour_physique.quantite_retournee,
            motif="Rebut / destruction - non récupérable",
            document_origine=self.retour_physique.reclamation.numero,
            utilisateur=self.controle_par,
        )
        CoutRetourPerte.objects.get_or_create(
            reclamation=self.retour_physique.reclamation,
            defaults={"quantite_detruite": self.retour_physique.quantite_retournee},
        )


class StatutReconditionnement(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    TERMINE = "TERMINE", "Terminé"


class Reconditionnement(ValidationAvantEnregistrement, models.Model):
    """§8B du croquis : intervention nécessaire avant réintégration (Module Production/Stock)."""
    controle_retour = models.OneToOneField(
        ControleRetour, verbose_name="Contrôle de retour", on_delete=models.CASCADE,
        related_name="reconditionnement",
    )
    description = models.TextField("Description de l'intervention", blank=True)
    quantite_reconditionnee = models.DecimalField(
        "Quantité reconditionnée", max_digits=12, decimal_places=3,
        null=True, blank=True,
    )
    statut = models.CharField(
        "Statut", max_length=15, choices=StatutReconditionnement.choices,
        default=StatutReconditionnement.EN_ATTENTE,
    )
    traite_par = models.ForeignKey(
        Utilisateur, verbose_name="Traité par", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    date_traitement = models.DateTimeField("Date de traitement", null=True, blank=True)

    class Meta:
        verbose_name = "Reconditionnement"
        verbose_name_plural = "Reconditionnements"

    def __str__(self):
        return f"Reconditionnement {self.controle_retour.retour_physique.reclamation.numero} ({self.get_statut_display()})"

    def clean(self):
        if self.controle_retour_id and self.controle_retour.resultat != ResultatControle.RECUPERABLE_AVEC_INTERVENTION:
            raise ValidationError({"controle_retour": (
                "Un reconditionnement n'existe que pour un contrôle « Récupérable avec intervention »."
            )})
        if self.pk and valeur_en_base(self, "controle_retour") != self.controle_retour_id:
            raise ValidationError({"controle_retour": "Le contrôle d'un reconditionnement ne peut pas être changé."})
        if valeur_en_base(self, "statut") == StatutReconditionnement.TERMINE:
            raise ValidationError("Ce reconditionnement est terminé : il ne peut plus être modifié.")
        if self.quantite_reconditionnee is not None and self.controle_retour_id:
            maximum = self.controle_retour.retour_physique.quantite_retournee
            exiger_positif(self.quantite_reconditionnee, "quantite_reconditionnee", "La quantité reconditionnée")
            if self.quantite_reconditionnee > maximum:
                raise ValidationError({"quantite_reconditionnee": (
                    f"Quantité reconditionnée ({self.quantite_reconditionnee}) supérieure à la quantité retournée ({maximum})."
                )})

    def verifier_suppression(self):
        raise ValidationError("Un reconditionnement ne peut pas être supprimé (circuit de retour en cours ou terminé).")

    @transaction.atomic
    def terminer(self, utilisateur, quantite_reconditionnee, cout=None):
        """
        Termine le reconditionnement : réintègre la quantité traitée en
        stock disponible (impact automatique Stock) et enregistre le
        coût de l'intervention (impact automatique Coûts).
        Tout ou rien : une quantité absente/invalide ne laisse plus le
        reconditionnement « Terminé » sans réintégration.
        """
        from django.utils import timezone
        if self.statut == StatutReconditionnement.TERMINE:
            raise ValueError("Ce reconditionnement est déjà terminé.")
        quantite_reconditionnee = convertir_decimal(quantite_reconditionnee, "La quantité reconditionnée")
        cout = convertir_decimal(cout, "Le coût du reconditionnement", obligatoire=False, strict=False)
        self.quantite_reconditionnee = quantite_reconditionnee
        self.traite_par = utilisateur
        self.date_traitement = timezone.now()
        self.statut = StatutReconditionnement.TERMINE
        self.save()

        self.controle_retour._reintegrer_stock(quantite_reconditionnee)

        cout_retour, _ = CoutRetourPerte.objects.get_or_create(
            reclamation=self.controle_retour.retour_physique.reclamation,
        )
        cout_retour.cout_reconditionnement = cout
        cout_retour.save()


class CoutRetourPerte(ValidationAvantEnregistrement, models.Model):
    """
    §10 du croquis : coût des retours/pertes (Module Coûts). Créé
    automatiquement lors d'une sortie définitive (produit détruit) ou
    à la fin d'un reconditionnement (coût de l'intervention).
    """
    reclamation = models.OneToOneField(
        ReclamationClient, verbose_name="Réclamation", on_delete=models.CASCADE,
        related_name="cout_retour_perte",
    )
    quantite_detruite = models.DecimalField(
        "Quantité détruite", max_digits=12, decimal_places=3, null=True, blank=True,
    )
    cout_produit_detruit = models.DecimalField(
        "Coût du produit détruit", max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="À valoriser manuellement (dernier coût de revient connu de l'article).",
    )
    cout_reconditionnement = models.DecimalField(
        "Coût du reconditionnement", max_digits=14, decimal_places=2, null=True, blank=True,
    )
    date_enregistrement = models.DateTimeField("Date d'enregistrement", auto_now_add=True)

    class Meta:
        verbose_name = "Coût de retour / perte"
        verbose_name_plural = "Coûts de retours / pertes"

    def __str__(self):
        return f"Coût retour {self.reclamation.numero}"

    def clean(self):
        exiger_positif_optionnel(self.quantite_detruite, "quantite_detruite", "La quantité détruite")
        exiger_positif_optionnel(self.cout_produit_detruit, "cout_produit_detruit", "Le coût du produit détruit")
        exiger_positif_optionnel(self.cout_reconditionnement, "cout_reconditionnement", "Le coût du reconditionnement")


class TypeSolution(models.TextChoices):
    REMPLACEMENT = "REMPLACEMENT", "Remplacement"
    AVOIR = "AVOIR", "Avoir"
    REMBOURSEMENT = "REMBOURSEMENT", "Remboursement"


class SolutionClient(ValidationAvantEnregistrement, models.Model):
    """
    §9 du croquis (Module Commercial) : la solution apportée au client,
    une fois le produit contrôlé (ou même sans retour physique, ex :
    produit manquant). Impacts automatiques différents selon le type
    (§9A/9B/9C).
    """
    reclamation = models.OneToOneField(
        ReclamationClient, verbose_name="Réclamation", on_delete=models.CASCADE,
        related_name="solution",
    )
    type_solution = models.CharField("Type de solution", max_length=15, choices=TypeSolution.choices)

    # §9A Remplacement
    nouvelle_commande = models.ForeignKey(
        Commande, verbose_name="Nouvelle commande (remplacement)", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="remplacement_de_reclamations",
    )

    # §9B Avoir
    montant_avoir = models.DecimalField(
        "Montant de l'avoir", max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Crédit sur prochaine commande ou facture.",
    )

    # §9C Remboursement - voir limite connue en tête de fichier (pas de vrai modèle Décaissement encore)
    montant_rembourse = models.DecimalField(
        "Montant remboursé", max_digits=14, decimal_places=2, null=True, blank=True,
    )
    reference_sortie_caisse = models.CharField(
        "Référence de la sortie de caisse", max_length=100, blank=True,
        help_text="À renseigner manuellement en l'absence d'un module Décaissement dédié (voir README).",
    )

    autorise_par = models.ForeignKey(Utilisateur, verbose_name="Autorisé par", on_delete=models.PROTECT)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Solution apportée au client"
        verbose_name_plural = "Solutions apportées aux clients"

    def __str__(self):
        return f"Solution {self.reclamation.numero} - {self.get_type_solution_display()}"

    def save(self, *args, **kwargs):
        """
        À l'enregistrement de la solution, clôture automatiquement la
        réclamation (impact automatique Livraison), et déclenche
        l'impact automatique correspondant au type de solution :
        - AVOIR : crée un Avoir client (apps.commercial.Avoir)
        - REMBOURSEMENT : crée un Décaissement (apps.caisse.Decaissement)
          si une session de caisse est ouverte ; sinon reference_sortie_caisse
          reste à renseigner manuellement.
        """
        creation = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creation:
                if self.type_solution == TypeSolution.AVOIR:
                    self._creer_avoir()
                elif self.type_solution == TypeSolution.REMBOURSEMENT:
                    self._creer_decaissement()
                self.reclamation.cloturer()

    def clean(self):
        """
        - une solution se décide une seule fois, sur une réclamation non
          clôturée, et ne se modifie plus (avoir/décaissement déjà créés) ;
        - si le produit est revenu physiquement, il doit d'abord être contrôlé ;
        - chaque type exige son montant (et seulement le sien), au plus
          la valeur de la marchandise réclamée ;
        - la commande de remplacement doit être celle du même client.
        """
        if self.pk is not None:
            raise ValidationError("Une solution client enregistrée ne peut pas être modifiée.")
        if not self.reclamation_id:
            return
        reclamation = self.reclamation
        if reclamation.statut == StatutReclamation.CLOTUREE:
            raise ValidationError({"reclamation": f"La réclamation {reclamation.numero} est déjà clôturée."})
        retour = RetourPhysique.objects.filter(reclamation=reclamation).first()
        if retour is not None and retour.statut == StatutRetourPhysique.EN_QUARANTAINE:
            raise ValidationError({"reclamation": "Le produit retourné doit d'abord être contrôlé avant de décider de la solution."})

        valeur_reclamee = (
            reclamation.quantite * reclamation.prix_unitaire if reclamation.prix_unitaire is not None else None
        )
        montants = {
            TypeSolution.AVOIR: ("montant_avoir", "Le montant de l'avoir"),
            TypeSolution.REMBOURSEMENT: ("montant_rembourse", "Le montant remboursé"),
        }
        for type_solution, (champ, libelle) in montants.items():
            valeur = getattr(self, champ)
            if self.type_solution == type_solution:
                exiger_positif(valeur, champ, libelle)
                if valeur_reclamee is not None and valeur > valeur_reclamee:
                    raise ValidationError({champ: (
                        f"{libelle} ({valeur}) dépasse la valeur de la marchandise réclamée ({valeur_reclamee})."
                    )})
            elif valeur:
                raise ValidationError({champ: f"{libelle} ne concerne pas une solution de type « {self.get_type_solution_display()} »."})
        if self.nouvelle_commande_id:
            if self.type_solution != TypeSolution.REMPLACEMENT:
                raise ValidationError({"nouvelle_commande": "Une commande de remplacement ne concerne que le type « Remplacement »."})
            if self.nouvelle_commande.client_id != reclamation.client_id:
                raise ValidationError({"nouvelle_commande": "La commande de remplacement doit être au nom du même client."})

    def verifier_suppression(self):
        raise ValidationError("Une solution client ne peut pas être supprimée (réclamation clôturée, impacts déjà appliqués).")

    def _creer_avoir(self):
        from apps.commercial.models import Avoir
        # Toujours un NOUVEL avoir : auparavant un get_or_create par
        # (facture, client) réutilisait l'avoir d'une autre réclamation
        # (ex : deux réclamations sans facture pour le même client).
        Avoir.objects.create(
            facture_origine=self.reclamation.facture,
            client=self.reclamation.client,
            montant=self.montant_avoir,
            motif=f"Réclamation {self.reclamation.numero}",
            cree_par=self.autorise_par,
        )

    def _creer_decaissement(self):
        """
        Crée le décaissement sur une session ouverte disposant d'assez
        d'argent, effectué par le caissier de cette session et autorisé
        par la personne qui décide la solution. Sans session adaptée, la
        référence reste à renseigner manuellement (comme auparavant).
        """
        from apps.caisse.models import SessionCaisse, Decaissement
        session_ouverte = next(
            (
                session for session in SessionCaisse.objects.filter(statut="OUVERTE").order_by("date_ouverture")
                if session.calculer_solde_theorique() >= self.montant_rembourse
                and session.caissier_id != self.autorise_par_id
            ),
            None,
        )
        if not session_ouverte:
            return
        decaissement = Decaissement.objects.create(
            session_caisse=session_ouverte, montant=self.montant_rembourse,
            motif=f"Remboursement réclamation {self.reclamation.numero}",
            beneficiaire=self.reclamation.client.nom,
            autorise_par=self.autorise_par, effectue_par=session_ouverte.caissier,
        )
        self.reference_sortie_caisse = decaissement.numero
        super().save(update_fields=["reference_sortie_caisse"])
