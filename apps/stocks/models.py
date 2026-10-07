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


class TypeLieu(models.TextChoices):
    """Guide du paramétrage §5 : le stock usine reste distinct du stock des dépôts extérieurs."""
    MAGASIN_MATIERES = "MAGASIN_MATIERES", "Magasin matières (usine)"
    STOCK_USINE = "STOCK_USINE", "Stock usine (produits finis)"
    DEPOT_EXTERIEUR = "DEPOT_EXTERIEUR", "Dépôt extérieur / point de vente"
    QUARANTAINE = "QUARANTAINE", "Quarantaine"


TYPES_DEPOTS_SYSTEME = {
    "Magasin principal": TypeLieu.MAGASIN_MATIERES,
    "Dépôt produits finis": TypeLieu.STOCK_USINE,
    "Quarantaine": TypeLieu.QUARANTAINE,
}


class Depot(ValidationAvantEnregistrement, models.Model):
    """
    Un lieu de stockage : magasin matières ou stock produits finis d'une
    usine, dépôt extérieur (point de vente), quarantaine. On paramètre le
    lieu et ses règles, jamais sa quantité (calculée par les mouvements).
    """
    code = models.CharField("Code", max_length=30, unique=True, null=True, blank=True, editable=False)
    nom = models.CharField("Nom du dépôt", max_length=100)
    type_lieu = models.CharField("Type de lieu", max_length=20, choices=TypeLieu.choices, default=TypeLieu.DEPOT_EXTERIEUR)
    usine = models.ForeignKey(
        "industriel.Usine", verbose_name="Usine de rattachement", on_delete=models.PROTECT,
        null=True, blank=True, related_name="lieux_stockage",
    )
    activite = models.ForeignKey(
        "industriel.Activite", verbose_name="Activité", on_delete=models.PROTECT,
        null=True, blank=True, related_name="lieux_stockage", help_text="Vide = toutes activités.",
    )
    articles_autorises = models.ManyToManyField(
        Article, verbose_name="Articles autorisés", blank=True, related_name="lieux_autorises",
        help_text="Vide = tous les articles.",
    )
    gestion_lots = models.BooleanField("Gestion des lots", default=True)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Dépôt"
        verbose_name_plural = "Dépôts"

    def __str__(self):
        return self.nom

    PREFIXES_CODE = {
        TypeLieu.MAGASIN_MATIERES: "MAG", TypeLieu.STOCK_USINE: "ST",
        TypeLieu.DEPOT_EXTERIEUR: "DEP", TypeLieu.QUARANTAINE: "QUA",
    }

    def save(self, *args, **kwargs):
        if not self.code:
            from apps.core.models import generer_code_unique
            self.code = generer_code_unique(Depot, self.PREFIXES_CODE.get(self.type_lieu, "LIEU"), largeur=3)
        super().save(*args, **kwargs)

    @property
    def est_systeme(self):
        return self.nom in DEPOTS_SYSTEME

    def accepte(self, article):
        """L'article peut-il être stocké ici ?"""
        if self.activite_id and article.activite_id and article.activite_id != self.activite_id:
            return False
        return not self.pk or not self.articles_autorises.exists() or self.articles_autorises.filter(pk=article.pk).exists()

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
            if self.type_lieu != TYPES_DEPOTS_SYSTEME[ancien_nom]:
                raise ValidationError({"type_lieu": f"« {ancien_nom} » est un dépôt système : son type est fixe."})
        if self.type_lieu in (TypeLieu.MAGASIN_MATIERES, TypeLieu.STOCK_USINE) and not self.usine_id \
                and self.nom not in DEPOTS_SYSTEME:
            raise ValidationError({"usine": "Un magasin matières ou un stock usine est rattaché à une usine."})

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
    depot, _ = Depot.objects.get_or_create(
        nom=nom, defaults={"actif": True, "type_lieu": TYPES_DEPOTS_SYSTEME.get(nom, TypeLieu.DEPOT_EXTERIEUR)},
    )
    return depot


def depot_matieres(usine=None):
    """Magasin matières de l'usine s'il est paramétré, sinon « Magasin principal »."""
    if usine is not None and usine.magasin_matieres_id:
        return usine.magasin_matieres
    return depot_par_defaut("Magasin principal")


def depot_produits_finis(usine=None):
    """Stock produits finis de l'usine s'il est paramétré, sinon « Dépôt produits finis »."""
    if usine is not None and usine.stock_produits_finis_id:
        return usine.stock_produits_finis
    return depot_par_defaut("Dépôt produits finis")


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
        entree = self.type_mouvement in (TypeMouvement.ENTREE, TypeMouvement.RETOUR) or (
            self.type_mouvement == TypeMouvement.AJUSTEMENT and self.quantite > 0
        )
        if entree and not self.depot.accepte(self.article):
            raise ValidationError({"depot": (
                f"{self.article.code} n'est pas autorisé dans le lieu « {self.depot.nom} » (articles / activité autorisés)."
            )})

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


class StatutTransfert(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    EXPEDIE = "EXPEDIE", "Expédié (en transit)"
    RECU = "RECU", "Reçu"
    ANNULE = "ANNULE", "Annulé"


class TransfertStock(ValidationAvantEnregistrement, models.Model):
    """
    Bon de transfert entre deux lieux (stock usine -> dépôt extérieur...).
    Le stock bouge vraiment : l'expédition SORT la marchandise du lieu
    source, la réception (confirmée au dépôt) l'ENTRE dans le lieu de
    destination, au coût moyen de la sortie. Entre les deux, elle est en
    transit (dans aucun des deux stocks).
    """
    numero = models.CharField("N° bon de transfert", max_length=30, unique=True, editable=False)
    depot_source = models.ForeignKey(Depot, verbose_name="Lieu source", on_delete=models.PROTECT, related_name="transferts_sortants")
    depot_destination = models.ForeignKey(Depot, verbose_name="Lieu de destination", on_delete=models.PROTECT, related_name="transferts_entrants")
    statut = models.CharField("Statut", max_length=20, choices=StatutTransfert.choices, default=StatutTransfert.BROUILLON)
    observations = models.TextField("Observations", blank=True)
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Créé par", on_delete=models.PROTECT, related_name="transferts_crees")
    expedie_par = models.ForeignKey(Utilisateur, verbose_name="Expédié par", on_delete=models.PROTECT, null=True, blank=True, related_name="transferts_expedies")
    recu_par = models.ForeignKey(Utilisateur, verbose_name="Reçu par", on_delete=models.PROTECT, null=True, blank=True, related_name="transferts_recus")
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    date_expedition = models.DateTimeField("Date d'expédition", null=True, blank=True)
    date_reception = models.DateTimeField("Date de réception", null=True, blank=True)

    class Meta:
        verbose_name = "Bon de transfert"
        verbose_name_plural = "Bons de transfert"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero} : {self.depot_source} -> {self.depot_destination}"

    TRANSITIONS = {
        StatutTransfert.BROUILLON: {StatutTransfert.EXPEDIE, StatutTransfert.ANNULE},
        StatutTransfert.EXPEDIE: {StatutTransfert.RECU},
    }

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("BT")
        super().save(*args, **kwargs)

    def clean(self):
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutTransfert.RECU, StatutTransfert.ANNULE):
            raise ValidationError(f"Le transfert {self.numero} est {self.get_statut_display().lower()} : il ne peut plus être modifié.")
        verifier_transition(ancien_statut, self.statut, self.TRANSITIONS, "statut du transfert", initial=StatutTransfert.BROUILLON)
        if self.depot_source_id and self.depot_source_id == self.depot_destination_id:
            raise ValidationError({"depot_destination": "Le lieu de destination doit être différent du lieu source."})
        for champ in ("depot_source", "depot_destination"):
            depot = getattr(self, champ) if getattr(self, f"{champ}_id") else None
            if depot is not None and not depot.actif:
                raise ValidationError({champ: f"Le lieu « {depot.nom} » est inactif."})
        if ancien_statut not in (None, StatutTransfert.BROUILLON):
            for champ in ("depot_source", "depot_destination"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Un transfert expédié ne change plus de lieux."})

    def verifier_suppression(self):
        if self.statut != StatutTransfert.BROUILLON:
            raise ValidationError("Seul un transfert en brouillon peut être supprimé (sinon : annulez-le avant expédition).")

    @transaction.atomic
    def expedier(self, utilisateur):
        """Sortie du lieu source (tout ou rien : contrôle du stock disponible ligne par ligne)."""
        from django.utils import timezone
        if self.statut != StatutTransfert.BROUILLON:
            raise ValueError("Seul un transfert en brouillon peut être expédié.")
        lignes = list(self.lignes.select_related("article"))
        if not lignes:
            raise ValueError("Ce transfert n'a aucune ligne.")
        self.statut = StatutTransfert.EXPEDIE
        self.expedie_par = utilisateur
        self.date_expedition = timezone.now()
        self.save()
        for ligne in lignes:
            if not self.depot_destination.accepte(ligne.article):
                raise ValueError(f"{ligne.article.code} n'est pas autorisé dans « {self.depot_destination.nom} ».")
            disponible = StockArticle.objects.filter(article=ligne.article, depot=self.depot_source).first()
            lots_a_sortir = ligne.article.type_article == "PRODUIT_FINI" and disponible is not None \
                and disponible.quantite_disponible >= ligne.quantite
            if lots_a_sortir:
                # Lots transférés : celui imposé (ou de la palette), sinon les plus proches de leur DLC.
                sortir_lots(ligne.article, self.depot_source, ligne.quantite, f"Transfert vers {self.depot_destination.nom}",
                            self.numero, lot_impose=ligne.lot, ligne_transfert=ligne)
            mouvement = MouvementStock.objects.create(
                article=ligne.article, depot=self.depot_source, type_mouvement=TypeMouvement.SORTIE,
                quantite=ligne.quantite, motif=f"Transfert vers {self.depot_destination.nom}",
                document_origine=self.numero, utilisateur=utilisateur,
            )
            ligne.cout_unitaire = mouvement.cout_unitaire
            ligne.save(update_fields=["cout_unitaire"])
            if ligne.palette_id:
                Palette.objects.filter(pk=ligne.palette_id).update(statut=StatutPalette.EN_TRANSIT, emplacement=None)

    @transaction.atomic
    def receptionner(self, utilisateur):
        """Confirmation de réception au dépôt : entrée dans le lieu de destination au coût de la sortie."""
        from django.utils import timezone
        if self.statut != StatutTransfert.EXPEDIE:
            raise ValueError("Seul un transfert expédié peut être réceptionné.")
        self.statut = StatutTransfert.RECU
        self.recu_par = utilisateur
        self.date_reception = timezone.now()
        self.save()
        for ligne in self.lignes.select_related("article"):
            MouvementStock.objects.create(
                article=ligne.article, depot=self.depot_destination, type_mouvement=TypeMouvement.ENTREE,
                quantite=ligne.quantite, cout_unitaire=ligne.cout_unitaire,
                motif=f"Transfert depuis {self.depot_source.nom}", document_origine=self.numero, utilisateur=utilisateur,
            )
            for sortie in ligne.mouvements_lot.filter(quantite__lt=0):
                MouvementLot.objects.create(
                    lot_id=sortie.lot_id, depot=self.depot_destination, quantite=-sortie.quantite,
                    motif=f"Transfert depuis {self.depot_source.nom}", document_origine=self.numero, ligne_transfert=ligne,
                )
            if ligne.palette_id:
                Palette.objects.filter(pk=ligne.palette_id).update(statut=StatutPalette.EN_STOCK, depot=self.depot_destination)

    def annuler(self):
        if self.statut != StatutTransfert.BROUILLON:
            raise ValueError("Un transfert expédié ne s'annule plus : il doit être réceptionné.")
        self.statut = StatutTransfert.ANNULE
        self.save()


class LigneTransfert(ValidationAvantEnregistrement, models.Model):
    transfert = models.ForeignKey(TransfertStock, verbose_name="Transfert", on_delete=models.CASCADE, related_name="lignes")
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    lot = models.ForeignKey("qualite.Lot", verbose_name="Lot", on_delete=models.PROTECT, null=True, blank=True)
    palette = models.ForeignKey(
        "Palette", verbose_name="Palette", on_delete=models.PROTECT, null=True, blank=True, related_name="lignes_transfert",
        help_text="Transfert d'une palette entière : article, lot et quantité sont repris de la palette.",
    )
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
    cout_unitaire = models.DecimalField("Coût unitaire (à l'expédition)", max_digits=14, decimal_places=4, null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Ligne de transfert"
        verbose_name_plural = "Lignes de transfert"

    def __str__(self):
        return f"{self.transfert.numero} : {self.quantite} {self.article.code}"

    def clean(self):
        if self.palette_id:
            palette = self.palette
            if palette.statut != StatutPalette.EN_STOCK:
                raise ValidationError({"palette": f"La palette {palette.numero} n'est pas en stock."})
            if self.transfert_id and palette.depot_id != self.transfert.depot_source_id:
                raise ValidationError({"palette": f"La palette {palette.numero} n'est pas au lieu source du transfert."})
            self.lot_id, self.article_id, self.quantite = palette.lot_id, palette.lot.article_id, palette.quantite
        exiger_positif(self.quantite, "quantite", "La quantité")
        transfert = TransfertStock.objects.filter(pk=valeur_en_base(self, "transfert") or self.transfert_id).first()
        if transfert and transfert.statut != StatutTransfert.BROUILLON:
            raise ValidationError("Ce transfert n'est plus en brouillon : ses lignes sont figées.")
        if self.lot_id:
            if self.article_id and self.lot.article_id != self.article_id:
                raise ValidationError({"lot": "Ce lot ne correspond pas à l'article."})
            if self.lot.statut != "LIBERE":
                raise ValidationError({"lot": f"Le lot {self.lot.numero_lot} n'est pas libéré : il ne peut pas être transféré."})
        if self.transfert_id and self.article_id and TransfertStock.objects.filter(pk=self.transfert_id).exists():
            autres = LigneTransfert.objects.filter(transfert_id=self.transfert_id).exclude(pk=self.pk)
            if self.palette_id and autres.filter(palette_id=self.palette_id).exists():
                raise ValidationError({"palette": "Cette palette figure déjà dans le transfert."})
            if not self.palette_id and autres.filter(article_id=self.article_id, lot_id=self.lot_id, palette__isnull=True).exists():
                raise ValidationError({"article": "Cet article (et ce lot) figure déjà dans le transfert."})

    def verifier_suppression(self):
        if self.transfert.statut != StatutTransfert.BROUILLON:
            raise ValidationError("Ce transfert n'est plus en brouillon : ses lignes sont figées.")


class StatutLotMatiere(models.TextChoices):
    A_CONTROLER = "A_CONTROLER", "À contrôler (réception)"
    LIBERE = "LIBERE", "Libéré"
    BLOQUE = "BLOQUE", "Bloqué"
    EPUISE = "EPUISE", "Épuisé"


class LotMatiere(ValidationAvantEnregistrement, models.Model):
    """
    Lot d'une matière, d'un emballage ou d'un consommable, avec son lot
    fournisseur et sa DLC. Créé à la réception (ou à la saisie d'un stock
    initial) ; consommé par les sorties matières des OF, les plus proches
    de leur DLC d'abord (puis les plus anciens). Un lot « à contrôler »
    ou « bloqué » est indisponible (quantité bloquée dans le stock).
    """
    numero = models.CharField("N° lot interne", max_length=30, unique=True, editable=False)
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT, related_name="lots_matieres")
    depot = models.ForeignKey(Depot, verbose_name="Lieu de stockage", on_delete=models.PROTECT, related_name="lots_matieres")
    lot_fournisseur = models.CharField("N° lot fournisseur", max_length=60, blank=True)
    fournisseur = models.ForeignKey("achats.Fournisseur", verbose_name="Fournisseur", on_delete=models.PROTECT, null=True, blank=True, related_name="lots_livres")
    ligne_reception = models.ForeignKey(
        "achats.LigneReceptionAchat", verbose_name="Réception", on_delete=models.PROTECT, null=True, blank=True, related_name="lots",
    )
    date_reception = models.DateField("Date de réception")
    date_peremption = models.DateField("DLC / DLUO", null=True, blank=True)
    quantite_initiale = models.DecimalField("Quantité reçue", max_digits=14, decimal_places=3)
    quantite_restante = models.DecimalField("Quantité restante", max_digits=14, decimal_places=3, editable=False)
    statut = models.CharField("Statut", max_length=20, choices=StatutLotMatiere.choices, default=StatutLotMatiere.LIBERE)
    observations = models.TextField("Observations", blank=True)
    date_creation = models.DateTimeField("Créé le", auto_now_add=True)

    class Meta:
        verbose_name = "Lot matière"
        verbose_name_plural = "Lots matières"
        ordering = ["date_peremption", "date_reception", "pk"]

    def __str__(self):
        fournisseur = f" (fourn. {self.lot_fournisseur})" if self.lot_fournisseur else ""
        return f"{self.numero} - {self.article.code}{fournisseur}"

    TRANSITIONS = {
        StatutLotMatiere.A_CONTROLER: {StatutLotMatiere.LIBERE, StatutLotMatiere.BLOQUE, StatutLotMatiere.EPUISE},
        StatutLotMatiere.LIBERE: {StatutLotMatiere.BLOQUE, StatutLotMatiere.EPUISE},
        StatutLotMatiere.BLOQUE: {StatutLotMatiere.LIBERE, StatutLotMatiere.EPUISE},
        StatutLotMatiere.EPUISE: {StatutLotMatiere.LIBERE},
    }
    INDISPONIBLES = (StatutLotMatiere.A_CONTROLER, StatutLotMatiere.BLOQUE)

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("LM")
        if self._state.adding and self.quantite_restante is None:
            self.quantite_restante = self.quantite_initiale
        ancien = valeur_en_base(self, "statut")
        with transaction.atomic():
            super().save(*args, **kwargs)
            self._repercuter_blocage(ancien)

    def clean(self):
        exiger_positif(self.quantite_initiale, "quantite_initiale", "La quantité reçue")
        if self.date_peremption and self.date_reception and self.date_peremption < self.date_reception:
            raise ValidationError({"date_peremption": "La DLC ne peut pas précéder la réception."})
        ancien = valeur_en_base(self, "statut")
        verifier_transition(ancien, self.statut, self.TRANSITIONS, "statut du lot matière")
        if ancien is None and not self.ligne_reception_id and self.article_id and self.depot_id:
            # Lot saisi sur un stock déjà présent (stock initial sans lot) : on ne
            # peut pas « loter » plus que le stock physique non encore loti.
            from django.db.models import Sum
            stock = StockArticle.objects.filter(article_id=self.article_id, depot_id=self.depot_id).first()
            physique = stock.quantite_physique if stock else 0
            deja = LotMatiere.objects.filter(article_id=self.article_id, depot_id=self.depot_id).exclude(
                statut=StatutLotMatiere.EPUISE,
            ).aggregate(t=Sum("quantite_restante"))["t"] or 0
            if self.quantite_initiale > physique - deja:
                raise ValidationError({"quantite_initiale": (
                    f"Seulement {physique - deja} de {self.article.code} au « {self.depot.nom} » ne sont rattachés à aucun lot."
                )})
        if ancien is not None:
            for champ in ("article", "depot"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "L'article et le lieu d'un lot ne changent plus."})
            if valeur_en_base(self, "quantite_initiale") != self.quantite_initiale:
                raise ValidationError({"quantite_initiale": "La quantité reçue d'un lot ne change plus."})

    def verifier_suppression(self):
        raise ValidationError("Un lot matière ne se supprime pas (traçabilité).")

    def _repercuter_blocage(self, ancien):
        """Un lot à contrôler / bloqué rend sa quantité restante indisponible dans le stock du lieu."""
        avant = ancien in self.INDISPONIBLES
        apres = self.statut in self.INDISPONIBLES
        if avant == apres:
            return
        stock, _ = StockArticle.objects.select_for_update().get_or_create(article_id=self.article_id, depot_id=self.depot_id)
        if apres:
            stock.quantite_bloquee += self.quantite_restante
        else:
            stock.quantite_bloquee = max(stock.quantite_bloquee - self.quantite_restante, 0)
        stock.save()

    @property
    def est_perime(self):
        from django.utils import timezone
        return bool(self.date_peremption and self.date_peremption < timezone.localdate())

    def changer_statut(self, statut):
        self.statut = statut
        self.save()

    def consommer(self, quantite):
        self.quantite_restante -= quantite
        if self.quantite_restante <= 0:
            self.quantite_restante = 0
            self.statut = StatutLotMatiere.EPUISE
        self.save()

    def restituer(self, quantite):
        self.quantite_restante += quantite
        if self.statut == StatutLotMatiere.EPUISE:
            self.statut = StatutLotMatiere.LIBERE
        elif self.statut in self.INDISPONIBLES:
            # Retour dans un lot bloqué entre-temps : la quantité retournée est bloquée aussi.
            stock, _ = StockArticle.objects.select_for_update().get_or_create(article_id=self.article_id, depot_id=self.depot_id)
            stock.quantite_bloquee += quantite
            stock.save()
        self.save()

    def retirer(self, quantite):
        """Retour fournisseur : la quantité quitte le lot (et son blocage éventuel)."""
        if self.statut in self.INDISPONIBLES:
            stock = StockArticle.objects.select_for_update().filter(article_id=self.article_id, depot_id=self.depot_id).first()
            if stock is not None:
                stock.quantite_bloquee = max(stock.quantite_bloquee - quantite, 0)
                stock.save()
        self.quantite_restante -= quantite
        if self.quantite_restante <= 0:
            self.quantite_restante = 0
            self.statut = StatutLotMatiere.EPUISE
        self.save()

    @classmethod
    def allouer(cls, article, depot, quantite, lot_impose=None):
        """
        Lots à consommer pour sortir `quantite` : [(lot, quantité)].
        Ordre : DLC la plus proche, puis réception la plus ancienne (FEFO).
        Lots périmés, à contrôler ou bloqués exclus. La part non couverte
        par des lots ne peut venir que du stock sans lot (stock antérieur
        au suivi par lot) ; sinon la sortie est refusée.
        """
        from decimal import Decimal
        from django.db.models import Sum
        from django.utils import timezone
        quantite = Decimal(quantite)
        if lot_impose is not None:
            if lot_impose.article_id != article.pk or lot_impose.depot_id != depot.pk:
                raise ValidationError({"lot_matiere": f"Le lot {lot_impose.numero} n'est pas un lot de {article.code} dans « {depot.nom} »."})
            if lot_impose.statut != StatutLotMatiere.LIBERE:
                raise ValidationError({"lot_matiere": f"Le lot {lot_impose.numero} est « {lot_impose.get_statut_display()} »."})
            if lot_impose.est_perime:
                raise ValidationError({"lot_matiere": f"Le lot {lot_impose.numero} est périmé ({lot_impose.date_peremption})."})
            if lot_impose.quantite_restante < quantite:
                raise ValidationError({"lot_matiere": f"Le lot {lot_impose.numero} ne contient plus que {lot_impose.quantite_restante}."})
            return [(lot_impose, quantite)]
        lots = cls.objects.select_for_update().filter(
            article=article, depot=depot, statut=StatutLotMatiere.LIBERE, quantite_restante__gt=0,
        ).exclude(date_peremption__lt=timezone.localdate()).order_by(
            models.F("date_peremption").asc(nulls_last=True), "date_reception", "pk",
        )
        allocation, reste = [], quantite
        for lot in lots:
            if reste <= 0:
                break
            prise = min(lot.quantite_restante, reste)
            allocation.append((lot, prise))
            reste -= prise
        if reste > 0:
            stock = StockArticle.objects.filter(article=article, depot=depot).first()
            physique = stock.quantite_physique if stock else Decimal(0)
            sous_lots = cls.objects.filter(article=article, depot=depot).exclude(
                statut=StatutLotMatiere.EPUISE,
            ).aggregate(t=Sum("quantite_restante"))["t"] or Decimal(0)
            sans_lot = physique - sous_lots
            if reste > sans_lot:
                raise ValidationError({"quantite_sortie": (
                    f"{article.code} : {quantite - reste} disponible dans des lots libérés non périmés "
                    f"et {max(sans_lot, 0)} hors lot au « {depot.nom} » ; sortie de {quantite} impossible."
                )})
        return allocation


# =====================================================================
# Stock par lot de produit fini, palettes et emplacements
# (schéma Jus : « stockage par lot, gestion des emplacements,
# traçabilité » ; rappel de lot jusqu'au client).
# =====================================================================

class MouvementLot(models.Model):
    """
    Quantité d'un lot de produit fini entrée (+) ou sortie (-) d'un lieu :
    libération, transfert, vente. Le solde par (lot, lieu) donne le stock
    du lot ; une sortie pour vente garde la ligne de commande, donc le
    client (traçabilité aval pour un rappel).
    """
    lot = models.ForeignKey("qualite.Lot", verbose_name="Lot", on_delete=models.PROTECT, related_name="mouvements_lot")
    depot = models.ForeignKey(Depot, verbose_name="Lieu", on_delete=models.PROTECT, related_name="mouvements_lot")
    quantite = models.DecimalField("Quantité (+ entrée / - sortie)", max_digits=14, decimal_places=3)
    motif = models.CharField("Motif", max_length=200)
    document_origine = models.CharField("Document", max_length=100, blank=True)
    ligne_commande = models.ForeignKey(
        "commercial.LigneCommande", verbose_name="Vente (ligne de commande)", on_delete=models.PROTECT,
        null=True, blank=True, related_name="lots_livres",
    )
    ligne_transfert = models.ForeignKey("LigneTransfert", verbose_name="Transfert", on_delete=models.PROTECT, null=True, blank=True, related_name="mouvements_lot")
    date = models.DateTimeField("Date", auto_now_add=True)

    class Meta:
        verbose_name = "Mouvement de lot (produit fini)"
        verbose_name_plural = "Mouvements de lots (produits finis)"
        ordering = ["date", "pk"]

    def __str__(self):
        return f"{self.lot.numero_lot} {self.quantite:+} @ {self.depot.nom}"


def solde_lot(lot, depot):
    from django.db.models import Sum
    return MouvementLot.objects.filter(lot=lot, depot=depot).aggregate(t=Sum("quantite"))["t"] or 0


def allouer_lots_produits_finis(article, depot, quantite, lot_impose=None):
    """
    Lots de produit fini à sortir pour `quantite` : [(lot, quantité)].
    Les lots libérés les plus proches de leur date de péremption sortent
    d'abord, puis les plus anciens. La part non couverte ne peut venir que
    du stock sans lot (stock antérieur au suivi par lot) ; sinon refus.
    """
    from decimal import Decimal
    from django.db.models import Sum
    from apps.qualite.models import Lot
    quantite = Decimal(quantite)
    soldes = (
        MouvementLot.objects.filter(depot=depot, lot__article=article)
        .values("lot").annotate(solde=Sum("quantite")).filter(solde__gt=0)
    )
    solde_par_lot = {ligne["lot"]: ligne["solde"] for ligne in soldes}
    if lot_impose is not None:
        disponible = solde_par_lot.get(lot_impose.pk, 0)
        if lot_impose.statut != "LIBERE":
            raise ValidationError({"lot": f"Le lot {lot_impose.numero_lot} n'est pas libéré."})
        if disponible < quantite:
            raise ValidationError({"lot": f"Il ne reste que {disponible} du lot {lot_impose.numero_lot} au « {depot.nom} »."})
        return [(lot_impose, quantite)]
    lots = Lot.objects.filter(pk__in=solde_par_lot, statut="LIBERE").order_by(
        models.F("date_peremption").asc(nulls_last=True), "date_production", "pk",
    )
    allocation, reste = [], quantite
    for lot in lots:
        if reste <= 0:
            break
        prise = min(solde_par_lot[lot.pk], reste)
        allocation.append((lot, prise))
        reste -= prise
    if reste > 0:
        stock = StockArticle.objects.filter(article=article, depot=depot).first()
        physique = stock.quantite_physique if stock else 0
        sans_lot = physique - sum(solde_par_lot.values(), Decimal(0))
        if reste > sans_lot:
            raise ValidationError({"quantite": (
                f"{article.code} : {quantite - reste} disponible dans des lots libérés et {max(sans_lot, 0)} hors lot "
                f"au « {depot.nom} » : sortie de {quantite} impossible (les lots bloqués ne sortent pas)."
            )})
    return allocation


def sortir_lots(article, depot, quantite, motif, document, lot_impose=None, **lien):
    """Alloue puis enregistre la sortie des lots (après contrôle du stock par le mouvement de stock)."""
    allocation = allouer_lots_produits_finis(article, depot, quantite, lot_impose=lot_impose)
    return [
        MouvementLot.objects.create(lot=lot, depot=depot, quantite=-prise, motif=motif, document_origine=document, **lien)
        for lot, prise in allocation
    ]


class Emplacement(ValidationAvantEnregistrement, models.Model):
    """Emplacement de stockage dans un lieu (allée, rack, niveau...)."""
    code = models.CharField("Code", max_length=40, unique=True, editable=False)
    depot = models.ForeignKey(Depot, verbose_name="Lieu", on_delete=models.PROTECT, related_name="emplacements")
    designation = models.CharField("Désignation", max_length=100, help_text="Ex : Allée A - Rack 2 - Niveau 1.")
    capacite_palettes = models.PositiveIntegerField("Capacité (palettes)", null=True, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Emplacement"
        verbose_name_plural = "Emplacements"
        ordering = ["depot", "code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.code:
            from apps.core.models import generer_code_unique
            self.code = generer_code_unique(Emplacement, f"{self.depot.code or 'LIEU'}-E", largeur=3)
        super().save(*args, **kwargs)

    def clean(self):
        if not (self.designation or "").strip():
            raise ValidationError({"designation": "La désignation de l'emplacement est obligatoire."})
        if self.pk and valeur_en_base(self, "depot") != self.depot_id and self.palettes.exists():
            raise ValidationError({"depot": "Cet emplacement contient des palettes : son lieu ne change pas."})

    @property
    def palettes_en_stock(self):
        return self.palettes.filter(statut=StatutPalette.EN_STOCK).count()


class StatutPalette(models.TextChoices):
    EN_STOCK = "EN_STOCK", "En stock"
    EN_TRANSIT = "EN_TRANSIT", "En transit"
    EXPEDIEE = "EXPEDIEE", "Expédiée / vendue"


class Palette(ValidationAvantEnregistrement, models.Model):
    """Palette identifiée (n° unique, étiquette avec code-barres), rattachée à son lot de produit fini."""
    numero = models.CharField("N° palette", max_length=30, unique=True, editable=False)
    lot = models.ForeignKey("qualite.Lot", verbose_name="Lot", on_delete=models.PROTECT, related_name="palettes")
    depot = models.ForeignKey(Depot, verbose_name="Lieu", on_delete=models.PROTECT, related_name="palettes")
    emplacement = models.ForeignKey(Emplacement, verbose_name="Emplacement", on_delete=models.PROTECT, null=True, blank=True, related_name="palettes")
    quantite = models.DecimalField("Quantité (unité de stock)", max_digits=14, decimal_places=3)
    statut = models.CharField("Statut", max_length=12, choices=StatutPalette.choices, default=StatutPalette.EN_STOCK)
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Constituée par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_creation = models.DateTimeField("Constituée le", auto_now_add=True)

    class Meta:
        verbose_name = "Palette"
        verbose_name_plural = "Palettes"
        ordering = ["-date_creation", "numero"]

    def __str__(self):
        return f"{self.numero} - {self.lot.numero_lot} ({self.quantite})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("PAL", largeur=8)
        super().save(*args, **kwargs)

    def clean(self):
        exiger_positif(self.quantite, "quantite", "La quantité de la palette")
        if self.emplacement_id and self.depot_id and self.emplacement.depot_id != self.depot_id:
            raise ValidationError({"emplacement": f"L'emplacement {self.emplacement.code} n'est pas dans « {self.depot.nom} »."})
        if self.emplacement_id and not self.emplacement.actif:
            raise ValidationError({"emplacement": f"L'emplacement {self.emplacement.code} est inactif."})
        if self.emplacement_id and self.emplacement.capacite_palettes and valeur_en_base(self, "emplacement") != self.emplacement_id \
                and self.emplacement.palettes_en_stock >= self.emplacement.capacite_palettes:
            raise ValidationError({"emplacement": f"L'emplacement {self.emplacement.code} est plein ({self.emplacement.capacite_palettes} palettes)."})

    @property
    def article(self):
        return self.lot.article

    @classmethod
    @transaction.atomic
    def constituer(cls, lot, utilisateur, quantite_par_palette=None):
        """
        Découpe un lot libéré en palettes : quantité par palette =
        packs par palette du produit (ou valeur fournie) ; la dernière peut
        être incomplète. Une seule fois par lot.
        """
        from decimal import Decimal, ROUND_DOWN
        if lot.statut != "LIBERE":
            raise ValueError("Seul un lot libéré (entré en stock) est palettisé.")
        if lot.palettes.exists():
            raise ValueError(f"Le lot {lot.numero_lot} est déjà palettisé.")
        article = lot.article
        if quantite_par_palette is None:
            if not article.packs_par_palette:
                raise ValueError(f"Renseignez les packs par palette de {article.code}, ou la quantité par palette.")
            unites = Decimal(article.packs_par_palette) * Decimal(article.unites_par_pack or 1)
            quantite_par_palette = (unites / article.facteur_unites).quantize(Decimal("0.001"), ROUND_DOWN)
        quantite_par_palette = Decimal(quantite_par_palette)
        if quantite_par_palette <= 0:
            raise ValueError("La quantité par palette doit être supérieure à 0.")
        reste, palettes = Decimal(lot.quantite), []
        while reste > 0:
            quantite = min(quantite_par_palette, reste)
            palettes.append(cls.objects.create(lot=lot, depot=lot.lieu_stock, quantite=quantite, cree_par=utilisateur))
            reste -= quantite
        return palettes
