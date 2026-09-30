# """
# Module 4 - Stocks.

# Gère les dépôts, les quantités par article/dépôt et tous les
# mouvements physiques (entrées, sorties, transferts, ajustements).

# Règle centrale du cahier des charges (§7.2) :
#     quantité disponible = quantité physique - quantité bloquée - quantité réservée
# """

# from django.db import models
# from apps.comptes.models import Utilisateur
# from apps.referentiel.models import Article
# from apps.core.models import generer_numero


# class Depot(models.Model):
#     """Un lieu de stockage physique (usine, dépôt régional...)."""
#     nom = models.CharField("Nom du dépôt", max_length=100)
#     adresse = models.CharField("Adresse", max_length=255, blank=True)
#     actif = models.BooleanField("Actif", default=True)

#     class Meta:
#         verbose_name = "Dépôt"
#         verbose_name_plural = "Dépôts"

#     def __str__(self):
#         return self.nom


# class StockArticle(models.Model):
#     """
#     La photographie de l'état du stock d'un article dans un dépôt à
#     l'instant présent. Mise à jour automatiquement à chaque mouvement
#     de stock (voir signal dans apps/stocks/signals.py).
#     """
#     article = models.ForeignKey(
#         Article, verbose_name="Article", on_delete=models.PROTECT,
#         related_name="stocks",
#     )
#     depot = models.ForeignKey(
#         Depot, verbose_name="Dépôt", on_delete=models.PROTECT,
#         related_name="stocks",
#     )
#     quantite_physique = models.DecimalField(
#         "Quantité physique", max_digits=14, decimal_places=3, default=0
#     )
#     quantite_bloquee = models.DecimalField(
#         "Quantité bloquée", max_digits=14, decimal_places=3, default=0,
#         help_text="Ex : lots non conformes en attente de décision qualité.",
#     )
#     quantite_reservee = models.DecimalField(
#         "Quantité réservée", max_digits=14, decimal_places=3, default=0,
#         help_text="Ex : réservée pour une commande client validée non encore livrée.",
#     )

#     class Meta:
#         verbose_name = "Stock par article"
#         verbose_name_plural = "Stocks par article"
#         unique_together = ("article", "depot")

#     def __str__(self):
#         return f"{self.article.code} @ {self.depot.nom} : {self.quantite_disponible} disponible"

#     @property
#     def quantite_disponible(self):
#         return self.quantite_physique - self.quantite_bloquee - self.quantite_reservee


# class TypeMouvement(models.TextChoices):
#     ENTREE = "ENTREE", "Entrée"
#     SORTIE = "SORTIE", "Sortie"
#     TRANSFERT = "TRANSFERT", "Transfert"
#     AJUSTEMENT = "AJUSTEMENT", "Ajustement (inventaire)"
#     RETOUR = "RETOUR", "Retour"


# class MouvementStock(models.Model):
#     """
#     Trace TOUTE variation physique de stock. Rien ne modifie
#     StockArticle directement : on passe toujours par un mouvement,
#     qui est ensuite répercuté automatiquement (traçabilité totale,
#     voir cahier des charges §16.1).
#     """
#     numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
#     article = models.ForeignKey(
#         Article, verbose_name="Article", on_delete=models.PROTECT,
#         related_name="mouvements",
#     )
#     depot = models.ForeignKey(
#         Depot, verbose_name="Dépôt", on_delete=models.PROTECT,
#         related_name="mouvements",
#     )
#     type_mouvement = models.CharField(
#         "Type de mouvement", max_length=20, choices=TypeMouvement.choices
#     )
#     quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
#     motif = models.CharField("Motif", max_length=255, blank=True)
#     document_origine = models.CharField(
#         "Document d'origine", max_length=100, blank=True,
#         help_text="Ex : numéro d'OF, de commande, de bon de livraison à l'origine du mouvement.",
#     )
#     utilisateur = models.ForeignKey(
#         Utilisateur, verbose_name="Effectué par", on_delete=models.PROTECT,
#     )
#     date_mouvement = models.DateTimeField("Date du mouvement", auto_now_add=True)

#     class Meta:
#         verbose_name = "Mouvement de stock"
#         verbose_name_plural = "Mouvements de stock"
#         ordering = ["-date_mouvement"]

#     def __str__(self):
#         return f"{self.numero} - {self.get_type_mouvement_display()} {self.quantite} {self.article.code}"

#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("MVT")
#         super().save(*args, **kwargs)


# class StatutInventaire(models.TextChoices):
#     EN_COURS = "EN_COURS", "En cours"
#     CLOTURE = "CLOTURE", "Clôturé"


# class Inventaire(models.Model):
#     """Une campagne d'inventaire physique sur un dépôt donné."""
#     depot = models.ForeignKey(Depot, verbose_name="Dépôt", on_delete=models.PROTECT)
#     date_inventaire = models.DateField("Date de l'inventaire")
#     statut = models.CharField(
#         "Statut", max_length=20, choices=StatutInventaire.choices,
#         default=StatutInventaire.EN_COURS,
#     )
#     cree_par = models.ForeignKey(Utilisateur, verbose_name="Réalisé par", on_delete=models.PROTECT)

#     class Meta:
#         verbose_name = "Inventaire"
#         verbose_name_plural = "Inventaires"

#     def __str__(self):
#         return f"Inventaire {self.depot.nom} du {self.date_inventaire}"


# class LigneInventaire(models.Model):
#     """
#     Compare la quantité théorique (celle du système) à la quantité
#     réellement comptée. L'écart déclenche un mouvement d'AJUSTEMENT.
#     """
#     inventaire = models.ForeignKey(
#         Inventaire, verbose_name="Inventaire", on_delete=models.CASCADE,
#         related_name="lignes",
#     )
#     article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
#     quantite_theorique = models.DecimalField("Quantité théorique", max_digits=14, decimal_places=3)
#     quantite_comptee = models.DecimalField("Quantité comptée", max_digits=14, decimal_places=3)

#     class Meta:
#         verbose_name = "Ligne d'inventaire"
#         verbose_name_plural = "Lignes d'inventaire"

#     def __str__(self):
#         return f"{self.inventaire} - {self.article.code}"

#     @property
#     def ecart(self):
#         return self.quantite_comptee - self.quantite_theorique


"""
Module 4 - Stocks.

Gère les dépôts, les quantités par article/dépôt et tous les
mouvements physiques (entrées, sorties, transferts, ajustements).

Règle centrale du cahier des charges (§7.2) :
    quantité disponible = quantité physique - quantité bloquée - quantité réservée
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, valeur_en_base, verifier_transition,
)


# Dépôts utilisés automatiquement par les autres modules, retrouvés PAR
# LEUR NOM (voir depot_par_defaut). Ils sont créés par la migration
# stocks/0002 et ne peuvent être ni renommés, ni désactivés, ni
# supprimés : sinon les mouvements automatiques iraient dans un nouveau
# dépôt vide (stock "introuvable", sorties refusées pour stock insuffisant).
DEPOTS_SYSTEME = {
    "Magasin principal": (
        "Matières premières et emballages : réceptions achats, sorties et "
        "retours matières de production, retours fournisseurs, réintégration "
        "des retours clients."
    ),
    "Dépôt produits finis": (
        "Produits finis : entrée à la libération qualité d'un lot, sortie "
        "magasin pour livraison."
    ),
    "Quarantaine": "Retours clients en attente de contrôle.",
}


class Depot(ValidationAvantEnregistrement, models.Model):
    """Un lieu de stockage physique (usine, dépôt régional...)."""
    nom = models.CharField("Nom du dépôt", max_length=100)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Dépôt"
        verbose_name_plural = "Dépôts"

    def __str__(self):
        return self.nom

    @property
    def est_systeme(self):
        return self.nom in DEPOTS_SYSTEME

    def clean(self):
        self.nom = (self.nom or "").strip()
        if not self.nom:
            raise ValidationError({"nom": "Le nom du dépôt est obligatoire."})
        if Depot.objects.filter(nom__iexact=self.nom).exclude(pk=self.pk).exists():
            raise ValidationError({"nom": f"Un dépôt nommé « {self.nom} » existe déjà."})
        ancien_nom = valeur_en_base(self, "nom")
        if ancien_nom in DEPOTS_SYSTEME:
            if self.nom != ancien_nom:
                raise ValidationError({"nom": (
                    f"« {ancien_nom} » est un dépôt système utilisé automatiquement par "
                    "les autres modules : il ne peut pas être renommé."
                )})
            if not self.actif:
                raise ValidationError({"actif": f"« {ancien_nom} » est un dépôt système : il ne peut pas être désactivé."})

    def verifier_suppression(self):
        if self.est_systeme:
            raise ValidationError(f"« {self.nom} » est un dépôt système : il ne peut pas être supprimé.")


def depot_par_defaut(nom):
    """
    Retourne le dépôt nommé `nom` (le crée s'il n'existe pas encore).

    Utilisé par les modules (production, qualité, achats,
    distribution) qui doivent générer un mouvement de stock
    automatique sans qu'un dépôt précis leur soit fourni par
    l'utilisateur - EVAM n'a qu'un seul site de production. Si EVAM
    ouvre plusieurs sites un jour, il faudra ajouter un vrai champ
    "dépôt" aux modèles concernés (SortieMatiere, Lot, ReceptionAchat,
    PreparationLivraison...) plutôt que de continuer à résoudre le
    dépôt par son nom.
    """
    depot, _ = Depot.objects.get_or_create(nom=nom, defaults={"actif": True})
    return depot


class StockArticle(models.Model):
    """
    La photographie de l'état du stock d'un article dans un dépôt à
    l'instant présent. Mise à jour automatiquement à chaque mouvement
    de stock (voir signal dans apps/stocks/signals.py).
    """
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.PROTECT,
        related_name="stocks",
    )
    depot = models.ForeignKey(
        Depot, verbose_name="Dépôt", on_delete=models.PROTECT,
        related_name="stocks",
    )
    quantite_physique = models.DecimalField(
        "Quantité physique", max_digits=14, decimal_places=3, default=0
    )
    quantite_bloquee = models.DecimalField(
        "Quantité bloquée", max_digits=14, decimal_places=3, default=0,
        help_text="Ex : lots non conformes en attente de décision qualité.",
    )
    quantite_reservee = models.DecimalField(
        "Quantité réservée", max_digits=14, decimal_places=3, default=0,
        help_text="Ex : réservée pour une commande client validée non encore livrée.",
    )

    class Meta:
        verbose_name = "Stock par article"
        verbose_name_plural = "Stocks par article"
        unique_together = ("article", "depot")

    def __str__(self):
        return f"{self.article.code} @ {self.depot.nom} : {self.quantite_disponible} disponible"

    @property
    def quantite_disponible(self):
        return self.quantite_physique - self.quantite_bloquee - self.quantite_reservee


class TypeMouvement(models.TextChoices):
    ENTREE = "ENTREE", "Entrée"
    SORTIE = "SORTIE", "Sortie"
    TRANSFERT = "TRANSFERT", "Transfert"
    AJUSTEMENT = "AJUSTEMENT", "Ajustement (inventaire)"
    RETOUR = "RETOUR", "Retour"


class MouvementStock(models.Model):
    """
    Trace TOUTE variation physique de stock. Rien ne modifie
    StockArticle directement : on passe toujours par un mouvement,
    qui est ensuite répercuté automatiquement (traçabilité totale,
    voir cahier des charges §16.1).
    """
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.PROTECT,
        related_name="mouvements",
    )
    depot = models.ForeignKey(
        Depot, verbose_name="Dépôt", on_delete=models.PROTECT,
        related_name="mouvements",
    )
    type_mouvement = models.CharField(
        "Type de mouvement", max_length=20, choices=TypeMouvement.choices
    )
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
    cout_unitaire = models.DecimalField(
        "Coût unitaire", max_digits=14, decimal_places=4, null=True, blank=True,
        help_text="Entrée : coût réel (prix d'achat, coût de revient de l'OF) ou, à défaut, coût moyen. "
                  "Sortie : toujours le coût moyen pondéré (CMUP) du moment.",
    )
    valeur = models.DecimalField("Valeur", max_digits=16, decimal_places=2, null=True, blank=True, editable=False)
    motif = models.CharField("Motif", max_length=255, blank=True)
    document_origine = models.CharField(
        "Document d'origine", max_length=100, blank=True,
        help_text="Ex : numéro d'OF, de commande, de bon de livraison à l'origine du mouvement.",
    )
    utilisateur = models.ForeignKey(
        Utilisateur, verbose_name="Effectué par", on_delete=models.PROTECT,
    )
    date_mouvement = models.DateTimeField("Date du mouvement", auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de stock"
        verbose_name_plural = "Mouvements de stock"
        ordering = ["-date_mouvement"]

    def __str__(self):
        return f"{self.numero} - {self.get_type_mouvement_display()} {self.quantite} {self.article.code}"

    def clean(self):
        """
        Un mouvement est un fait historique : seules les créations sont
        contrôlées ici (les modifications sont interdites par l'API).
        Règles :
        - quantité strictement positive (sauf AJUSTEMENT : non nulle,
          négative pour constater un manque d'inventaire) ;
        - une SORTIE ne peut pas dépasser la quantité DISPONIBLE du
          dépôt (physique - bloquée - réservée) : pas de stock négatif ;
        - un AJUSTEMENT négatif ne peut pas rendre le stock physique négatif ;
        - TRANSFERT refusé : ce type n'a aucun effet sur le stock (pas
          de dépôt destination), il se saisit en SORTIE + ENTREE.
        """
        if not self._state.adding:
            return
        if self.type_mouvement == TypeMouvement.TRANSFERT:
            raise ValidationError({"type_mouvement": (
                "Un transfert se saisit en deux mouvements : une SORTIE du dépôt "
                "source puis une ENTREE dans le dépôt destination."
            )})
        if self.type_mouvement == TypeMouvement.AJUSTEMENT:
            if self.quantite is None or self.quantite == 0:
                raise ValidationError({"quantite": "La quantité d'un ajustement ne peut pas être nulle."})
        else:
            exiger_positif(self.quantite, "quantite", "La quantité")

        if not (self.article_id and self.depot_id):
            return
        if not self.depot.actif:
            raise ValidationError({"depot": f"Le dépôt « {self.depot.nom} » est inactif."})

        stock = StockArticle.objects.filter(article_id=self.article_id, depot_id=self.depot_id).first()
        if self.type_mouvement == TypeMouvement.SORTIE:
            disponible = stock.quantite_disponible if stock else 0
            if self.quantite > disponible:
                raise ValidationError({"quantite": (
                    f"Stock insuffisant pour {self.article.code} au dépôt « {self.depot.nom} » : "
                    f"sortie demandée {self.quantite}, disponible {disponible}."
                )})
        if self.type_mouvement == TypeMouvement.AJUSTEMENT and self.quantite < 0:
            physique = stock.quantite_physique if stock else 0
            if physique + self.quantite < 0:
                raise ValidationError({"quantite": (
                    f"Ajustement impossible : le stock physique de {self.article.code} "
                    f"({physique}) deviendrait négatif."
                )})

    def save(self, *args, **kwargs):
        with transaction.atomic():
            creation = self._state.adding
            if creation and self.article_id and self.depot_id:
                # Verrouille la ligne de stock pendant le contrôle de
                # disponibilité (deux sorties simultanées ne peuvent pas
                # consommer deux fois le même stock).
                list(StockArticle.objects.select_for_update().filter(
                    article_id=self.article_id, depot_id=self.depot_id,
                ))
            self.clean()
            if not self.numero:
                self.numero = generer_numero("MVT")
            if creation:
                self._valoriser()
            super().save(*args, **kwargs)

    def _valoriser(self):
        """
        Coût moyen unitaire pondéré (CMUP), calculé par article tous dépôts
        confondus :
        - ENTREE / RETOUR / AJUSTEMENT positif : au coût fourni (achat,
          coût de revient...) ou, à défaut, au coût de référence ; le CMUP
          est recalculé : (stock x CMUP + quantité x coût) / (stock + quantité) ;
        - SORTIE / AJUSTEMENT négatif : au CMUP du moment (inchangé).
        """
        from decimal import Decimal
        from django.db.models import Sum
        valorisation, _ = ValorisationArticle.objects.select_for_update().get_or_create(
            article_id=self.article_id, defaults={"cout_unitaire_moyen": cout_de_reference(self.article)},
        )
        entree = self.type_mouvement in (TypeMouvement.ENTREE, TypeMouvement.RETOUR) or (
            self.type_mouvement == TypeMouvement.AJUSTEMENT and self.quantite > 0
        )
        if entree:
            if self.cout_unitaire is None:
                self.cout_unitaire = valorisation.cout_unitaire_moyen or cout_de_reference(self.article)
            stock_avant = StockArticle.objects.filter(article_id=self.article_id).aggregate(
                total=Sum("quantite_physique"),
            )["total"] or Decimal("0")
            stock_apres = stock_avant + self.quantite
            if stock_avant > 0 and stock_apres > 0:
                valorisation.cout_unitaire_moyen = (
                    stock_avant * valorisation.cout_unitaire_moyen + self.quantite * Decimal(self.cout_unitaire)
                ) / stock_apres
            else:
                valorisation.cout_unitaire_moyen = Decimal(self.cout_unitaire)
            valorisation.save()
        else:
            self.cout_unitaire = valorisation.cout_unitaire_moyen
        self.valeur = (Decimal(self.quantite) * Decimal(self.cout_unitaire)).quantize(Decimal("0.01"))


def cout_de_reference(article):
    """
    Coût à défaut, pour une entrée sans coût connu (stock initial, retour...) :
    dernier coût matière valorisé par la DAF, sinon dernier coût standard, sinon 0.
    """
    from decimal import Decimal
    from apps.couts.models import CoutMatiere, CoutStandard
    cout = CoutMatiere.objects.filter(article=article).order_by("-date_valorisation").first()
    if cout:
        return cout.cout_unitaire
    standard = CoutStandard.objects.filter(article=article).order_by("-date_debut_validite").first()
    return standard.cout_standard_unitaire if standard else Decimal("0")


class ValorisationArticle(models.Model):
    """Coût moyen unitaire pondéré (CMUP) courant d'un article, mis à jour à chaque entrée en stock."""
    article = models.OneToOneField(
        Article, verbose_name="Article", on_delete=models.CASCADE, related_name="valorisation",
    )
    cout_unitaire_moyen = models.DecimalField("Coût moyen unitaire pondéré", max_digits=14, decimal_places=4, default=0)
    date_mise_a_jour = models.DateTimeField("Mis à jour le", auto_now=True)

    class Meta:
        verbose_name = "Valorisation d'article (CMUP)"
        verbose_name_plural = "Valorisations d'articles (CMUP)"

    def __str__(self):
        return f"{self.article.code} : {self.cout_unitaire_moyen}"


class StatutInventaire(models.TextChoices):
    EN_COURS = "EN_COURS", "En cours"
    CLOTURE = "CLOTURE", "Clôturé"


class Inventaire(ValidationAvantEnregistrement, models.Model):
    """Une campagne d'inventaire physique sur un dépôt donné."""
    depot = models.ForeignKey(Depot, verbose_name="Dépôt", on_delete=models.PROTECT)
    date_inventaire = models.DateField("Date de l'inventaire")
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutInventaire.choices,
        default=StatutInventaire.EN_COURS,
    )
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Réalisé par", on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Inventaire"
        verbose_name_plural = "Inventaires"

    def __str__(self):
        return f"Inventaire {self.depot.nom} du {self.date_inventaire}"

    def save(self, *args, **kwargs):
        cloture = self.statut == StatutInventaire.CLOTURE and valeur_en_base(self, "statut") == StatutInventaire.EN_COURS
        with transaction.atomic():
            super().save(*args, **kwargs)
            if cloture:
                from apps.comptabilite.anomalies import controler_inventaire
                controler_inventaire(self)

    def clean(self):
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutInventaire.CLOTURE:
            raise ValidationError("Cet inventaire est clôturé : il ne peut plus être modifié.")
        verifier_transition(
            ancien_statut, self.statut,
            {StatutInventaire.EN_COURS: {StatutInventaire.CLOTURE}}, "statut d'inventaire",
            initial=StatutInventaire.EN_COURS,
        )


class LigneInventaire(ValidationAvantEnregistrement, models.Model):
    """
    Compare la quantité théorique (celle du système) à la quantité
    réellement comptée. L'écart déclenche un mouvement d'AJUSTEMENT.
    """
    inventaire = models.ForeignKey(
        Inventaire, verbose_name="Inventaire", on_delete=models.CASCADE,
        related_name="lignes",
    )
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    quantite_theorique = models.DecimalField("Quantité théorique", max_digits=14, decimal_places=3)
    quantite_comptee = models.DecimalField("Quantité comptée", max_digits=14, decimal_places=3)

    class Meta:
        verbose_name = "Ligne d'inventaire"
        verbose_name_plural = "Lignes d'inventaire"

    def __str__(self):
        return f"{self.inventaire} - {self.article.code}"

    def clean(self):
        exiger_positif(self.quantite_theorique, "quantite_theorique", "La quantité théorique", strict=False)
        exiger_positif(self.quantite_comptee, "quantite_comptee", "La quantité comptée", strict=False)
        if self.pk:
            ancien_inventaire = valeur_en_base(self, "inventaire")
            if Inventaire.objects.filter(pk=ancien_inventaire, statut=StatutInventaire.CLOTURE).exists():
                raise ValidationError("Cette ligne appartient à un inventaire clôturé : elle ne peut plus être modifiée.")
        if self.inventaire_id:
            if self.inventaire.statut == StatutInventaire.CLOTURE:
                raise ValidationError({"inventaire": "Cet inventaire est clôturé : on ne peut plus y ajouter de ligne."})
            if self.article_id and LigneInventaire.objects.filter(
                inventaire_id=self.inventaire_id, article_id=self.article_id,
            ).exclude(pk=self.pk).exists():
                raise ValidationError({"article": "Cet article a déjà une ligne dans cet inventaire."})

    @property
    def ecart(self):
        return self.quantite_comptee - self.quantite_theorique
