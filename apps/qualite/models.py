# """
# Module 6 - Qualité / Traçabilité.

# Contient le Lot (unité de traçabilité de toute production) et son
# contrôle qualité. Règle centrale du cahier des charges :

#     "Seuls les lots Libérés sont vendables."

# Le statut d'un lot ne peut progresser que dans un sens précis :
# EN_ATTENTE -> (CONFORME ou NON_CONFORME) -> LIBERE ou BLOQUE.
# Le passage à LIBERE est réservé au Responsable Qualité.
# """

# from django.db import models
# from apps.comptes.models import Utilisateur
# from apps.referentiel.models import Article
# from apps.core.models import generer_numero


# class StatutLot(models.TextChoices):
#     EN_ATTENTE = "EN_ATTENTE", "En attente"
#     CONFORME = "CONFORME", "Conforme"
#     NON_CONFORME = "NON_CONFORME", "Non conforme"
#     BLOQUE = "BLOQUE", "Bloqué"
#     LIBERE = "LIBERE", "Libéré"


# class Lot(models.Model):
#     """
#     Un lot = une quantité produite en une fois, traçable de bout en
#     bout (matières utilisées -> OF -> lot -> stock -> commande ->
#     client). Le numéro de lot est unique et généré automatiquement.
#     """
#     numero_lot = models.CharField(
#         "Numéro de lot", max_length=30, unique=True, editable=False
#     )
#     article = models.ForeignKey(
#         Article, verbose_name="Article", on_delete=models.PROTECT,
#         related_name="lots",
#     )
#     ordre_fabrication = models.ForeignKey(
#         "production.OrdreFabrication", verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="lots",
#         null=True, blank=True,
#     )
#     quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
#     statut = models.CharField(
#         "Statut", max_length=20, choices=StatutLot.choices,
#         default=StatutLot.EN_ATTENTE,
#     )
#     date_production = models.DateField("Date de production")
#     date_peremption = models.DateField("Date de péremption", null=True, blank=True)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Lot"
#         verbose_name_plural = "Lots"
#         ordering = ["-date_creation"]

#     def __str__(self):
#         return f"{self.numero_lot} - {self.article.designation} ({self.get_statut_display()})"

#     def save(self, *args, **kwargs):
#         if not self.numero_lot:
#             self.numero_lot = generer_numero("LOT")
#         super().save(*args, **kwargs)

#     @property
#     def est_vendable(self):
#         """Seuls les lots Libérés sont vendables (règle du cahier des charges)."""
#         return self.statut == StatutLot.LIBERE

#     def bloquer(self, motif=""):
#         self.statut = StatutLot.BLOQUE
#         self.save()

#     def liberer(self, utilisateur):
#         """
#         Ne peut être appelé que si le lot est Conforme.
#         La vérification du profil (Responsable Qualité) se fait au
#         niveau de la vue (permission_classes), pas ici.
#         """
#         if self.statut != StatutLot.CONFORME:
#             raise ValueError(
#                 "Seul un lot Conforme peut être libéré. "
#                 "Statut actuel : " + self.get_statut_display()
#             )
#         self.statut = StatutLot.LIBERE
#         self.save()


# class ControleQualite(models.Model):
#     """
#     Le contrôle effectué par le Responsable Qualité sur un lot,
#     qui détermine s'il devient Conforme ou Non conforme.
#     """
#     lot = models.OneToOneField(
#         Lot, verbose_name="Lot contrôlé", on_delete=models.CASCADE,
#         related_name="controle_qualite",
#     )
#     controleur = models.ForeignKey(
#         Utilisateur, verbose_name="Contrôlé par", on_delete=models.PROTECT,
#     )
#     resultat = models.CharField(
#         "Résultat", max_length=20,
#         choices=[("CONFORME", "Conforme"), ("NON_CONFORME", "Non conforme")],
#     )
#     observations = models.TextField("Observations", blank=True)
#     date_controle = models.DateTimeField("Date de contrôle", auto_now_add=True)

#     class Meta:
#         verbose_name = "Contrôle qualité"
#         verbose_name_plural = "Contrôles qualité"

#     def __str__(self):
#         return f"Contrôle {self.lot.numero_lot} - {self.resultat}"

#     def save(self, *args, **kwargs):
#         """A chaque contrôle enregistré, met à jour automatiquement le
#         statut du lot correspondant."""
#         super().save(*args, **kwargs)
#         self.lot.statut = self.resultat
#         self.lot.save()


"""
Module 6 - Qualité / Traçabilité.

Contient le Lot (unité de traçabilité de toute production) et son
contrôle qualité. Règle centrale du cahier des charges :

    "Seuls les lots Libérés sont vendables."

Le statut d'un lot ne peut progresser que dans un sens précis :
EN_ATTENTE -> (CONFORME ou NON_CONFORME) -> LIBERE ou BLOQUE.
Le passage à LIBERE est réservé au Responsable Qualité.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_ordre_dates, valeur_en_base,
)


class StatutLot(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    CONFORME = "CONFORME", "Conforme"
    NON_CONFORME = "NON_CONFORME", "Non conforme"
    BLOQUE = "BLOQUE", "Bloqué"
    LIBERE = "LIBERE", "Libéré"


class Lot(ValidationAvantEnregistrement, models.Model):
    """
    Un lot = une quantité produite en une fois, traçable de bout en
    bout (matières utilisées -> OF -> lot -> stock -> commande ->
    client). Le numéro de lot est unique et généré automatiquement.
    """
    numero_lot = models.CharField(
        "Numéro de lot", max_length=30, unique=True, editable=False
    )
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.PROTECT,
        related_name="lots",
    )
    ordre_fabrication = models.ForeignKey(
        "production.OrdreFabrication", verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="lots",
        null=True, blank=True,
    )
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutLot.choices,
        default=StatutLot.EN_ATTENTE,
    )
    date_production = models.DateField("Date de production")
    date_peremption = models.DateField("Date de péremption", null=True, blank=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Lot"
        verbose_name_plural = "Lots"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero_lot} - {self.article.designation} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero_lot:
            self.numero_lot = generer_numero("LOT")
        super().save(*args, **kwargs)

    def clean(self):
        """
        - quantité strictement positive, péremption après production ;
        - le lot correspond à l'article de son OF, et un OF annulé ne
          produit pas de lot ;
        - quantité, article et OF ne changent plus une fois le lot
          contrôlé (son contrôle et son entrée en stock en dépendent).
        """
        exiger_positif(self.quantite, "quantite", "La quantité du lot")
        exiger_ordre_dates(
            self.date_production, self.date_peremption, "date_peremption",
            "la date de production", "La date de péremption",
        )
        if self.ordre_fabrication_id:
            of = self.ordre_fabrication
            if of.statut == "ANNULE":
                raise ValidationError({"ordre_fabrication": f"L'OF {of.numero} est annulé : il ne peut pas produire de lot."})
            if self.article_id and of.article_id != self.article_id:
                raise ValidationError({"article": f"L'article du lot doit être celui de l'OF {of.numero}."})
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut not in (None, StatutLot.EN_ATTENTE):
            for champ in ("article", "ordre_fabrication"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Ce lot a déjà été contrôlé : ce champ ne peut plus être modifié."})
            if valeur_en_base(self, "quantite") != self.quantite:
                raise ValidationError({"quantite": "Ce lot a déjà été contrôlé : sa quantité ne peut plus être modifiée."})
        if ancien_statut is None and self.statut != StatutLot.EN_ATTENTE:
            raise ValidationError({"statut": "Un lot est toujours créé « En attente » de contrôle qualité."})

    def verifier_suppression(self):
        if self.statut != StatutLot.EN_ATTENTE:
            raise ValidationError("Seul un lot en attente de contrôle peut être supprimé.")

    @property
    def est_vendable(self):
        """Seuls les lots Libérés sont vendables (règle du cahier des charges)."""
        return self.statut == StatutLot.LIBERE

    @transaction.atomic
    def bloquer(self, motif=""):
        """
        Bloque le lot. S'il était déjà libéré (donc entré en stock
        produits finis), sa quantité passe en « bloquée » dans ce stock :
        elle n'est plus disponible à la vente ni à la sortie.
        """
        if self.statut == StatutLot.BLOQUE:
            raise ValueError("Ce lot est déjà bloqué.")
        if self.statut == StatutLot.LIBERE:
            from apps.stocks.models import StockArticle, depot_par_defaut
            stock = StockArticle.objects.select_for_update().filter(
                article=self.article, depot=depot_par_defaut("Dépôt produits finis"),
            ).first()
            if stock is None or stock.quantite_disponible < self.quantite:
                disponible = stock.quantite_disponible if stock else 0
                raise ValueError(
                    f"Impossible de bloquer le lot {self.numero_lot} : il n'en reste que {disponible} "
                    f"disponible(s) en stock produits finis sur {self.quantite} (le reste a déjà été vendu/sorti)."
                )
            stock.quantite_bloquee += self.quantite
            stock.save()
        self.statut = StatutLot.BLOQUE
        self.save()

    @transaction.atomic
    def liberer(self, utilisateur):
        """
        Ne peut être appelé que si le lot est Conforme.
        La vérification du profil (Responsable Qualité) se fait au
        niveau de la vue (permission_classes), pas ici.

        La libération est le moment où le produit fini devient
        vendable (règle centrale du module) : elle doit donc faire
        ENTRER physiquement la quantité du lot dans le stock des
        produits finis, sans quoi aucune commande client ne pourrait
        jamais réserver/sortir ce lot alors même qu'il est "libéré".
        """
        if self.statut != StatutLot.CONFORME:
            raise ValueError(
                "Seul un lot Conforme peut être libéré. "
                "Statut actuel : " + self.get_statut_display()
            )
        self.statut = StatutLot.LIBERE
        self.save()
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        MouvementStock.objects.create(
            article=self.article,
            depot=depot_par_defaut("Dépôt produits finis"),
            type_mouvement=TypeMouvement.ENTREE,
            quantite=self.quantite,
            motif=f"Libération qualité du lot {self.numero_lot}",
            document_origine=self.numero_lot,
            utilisateur=utilisateur,
        )


class ControleQualite(ValidationAvantEnregistrement, models.Model):
    """
    Le contrôle effectué par le Responsable Qualité sur un lot,
    qui détermine s'il devient Conforme ou Non conforme.
    """
    lot = models.OneToOneField(
        Lot, verbose_name="Lot contrôlé", on_delete=models.CASCADE,
        related_name="controle_qualite",
    )
    controleur = models.ForeignKey(
        Utilisateur, verbose_name="Contrôlé par", on_delete=models.PROTECT,
    )
    resultat = models.CharField(
        "Résultat", max_length=20,
        choices=[("CONFORME", "Conforme"), ("NON_CONFORME", "Non conforme")],
    )
    observations = models.TextField("Observations", blank=True)
    date_controle = models.DateTimeField("Date de contrôle", auto_now_add=True)

    class Meta:
        verbose_name = "Contrôle qualité"
        verbose_name_plural = "Contrôles qualité"

    def __str__(self):
        return f"Contrôle {self.lot.numero_lot} - {self.resultat}"

    def clean(self):
        """
        Un lot libéré ou bloqué ne peut plus être (re)contrôlé :
        auparavant, modifier le contrôle d'un lot libéré le remettait à
        « Conforme », et on pouvait le libérer une 2e fois (double
        entrée en stock).
        """
        if self.pk and valeur_en_base(self, "lot") != self.lot_id:
            raise ValidationError({"lot": "Le lot d'un contrôle ne peut pas être changé."})
        if self.lot_id and self.lot.statut in (StatutLot.LIBERE, StatutLot.BLOQUE):
            raise ValidationError({"lot": (
                f"Le lot {self.lot.numero_lot} est {self.lot.get_statut_display().lower()} : "
                "son contrôle ne peut plus être créé ni modifié."
            )})

    def verifier_suppression(self):
        if self.lot.statut in (StatutLot.LIBERE, StatutLot.BLOQUE):
            raise ValidationError("Le lot est déjà libéré ou bloqué : son contrôle ne peut plus être supprimé.")

    def save(self, *args, **kwargs):
        """A chaque contrôle enregistré, met à jour automatiquement le
        statut du lot correspondant."""
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.lot.statut = self.resultat
            self.lot.save()
