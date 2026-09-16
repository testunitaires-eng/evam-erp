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

from django.db import models
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.commercial.models import Client, Facture, Commande
from apps.distribution.models import BonLivraison
from apps.qualite.models import Lot
from apps.core.models import generer_numero


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


class ReclamationClient(models.Model):
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

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("RCL")
        super().save(*args, **kwargs)

    def cloturer(self):
        """Clôture la réclamation (impact automatique §12 : suivi statut côté Livraison)."""
        from django.utils import timezone
        self.statut = StatutReclamation.CLOTUREE
        self.date_cloture = timezone.now()
        self.save()


class StatutRetourPhysique(models.TextChoices):
    EN_QUARANTAINE = "EN_QUARANTAINE", "En quarantaine"
    CONTROLE_EFFECTUE = "CONTROLE_EFFECTUE", "Contrôle effectué"


class RetourPhysique(models.Model):
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

    def save(self, *args, **kwargs):
        """À la création, enregistre l'entrée en quarantaine comme un mouvement de stock (impact automatique §12 : Stock)."""
        creation = self._state.adding
        super().save(*args, **kwargs)
        if creation:
            self._entree_en_quarantaine()

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


class ControleRetour(models.Model):
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

    def save(self, *args, **kwargs):
        creation = self._state.adding
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


class Reconditionnement(models.Model):
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

    def terminer(self, utilisateur, quantite_reconditionnee, cout=None):
        """
        Termine le reconditionnement : réintègre la quantité traitée en
        stock disponible (impact automatique Stock) et enregistre le
        coût de l'intervention (impact automatique Coûts).
        """
        from django.utils import timezone
        if self.statut == StatutReconditionnement.TERMINE:
            raise ValueError("Ce reconditionnement est déjà terminé.")
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


class CoutRetourPerte(models.Model):
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


class TypeSolution(models.TextChoices):
    REMPLACEMENT = "REMPLACEMENT", "Remplacement"
    AVOIR = "AVOIR", "Avoir"
    REMBOURSEMENT = "REMBOURSEMENT", "Remboursement"


class SolutionClient(models.Model):
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
        super().save(*args, **kwargs)
        if creation:
            if self.type_solution == TypeSolution.AVOIR and self.montant_avoir:
                self._creer_avoir()
            elif self.type_solution == TypeSolution.REMBOURSEMENT and self.montant_rembourse:
                self._creer_decaissement()
        self.reclamation.cloturer()

    def _creer_avoir(self):
        from apps.commercial.models import Avoir
        Avoir.objects.get_or_create(
            facture_origine=self.reclamation.facture,
            client=self.reclamation.client,
            defaults={
                "montant": self.montant_avoir,
                "motif": f"Réclamation {self.reclamation.numero}",
                "cree_par": self.autorise_par,
            },
        )

    def _creer_decaissement(self):
        from apps.caisse.models import SessionCaisse, Decaissement
        session_ouverte = SessionCaisse.objects.filter(statut="OUVERTE").first()
        if not session_ouverte:
            return
        decaissement = Decaissement.objects.create(
            session_caisse=session_ouverte, montant=self.montant_rembourse,
            motif=f"Remboursement réclamation {self.reclamation.numero}",
            beneficiaire=self.reclamation.client.nom,
            autorise_par=self.autorise_par, effectue_par=self.autorise_par,
        )
        self.reference_sortie_caisse = decaissement.numero
        super().save(update_fields=["reference_sortie_caisse"])