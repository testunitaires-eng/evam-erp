# """
# Module 5 - Production.

# Le cœur métier de l'application. Contient :
# - PlanProduction : ce qu'on prévoit de fabriquer
# - OrdreFabrication (OF) : l'exécution réelle, avec son workflow de
#   statuts (§8.3 du cahier des charges)
# - BesoinMatierePrevu : calculé AUTOMATIQUEMENT à partir de la fiche
#   technique quand un OF est lancé (§8.4)
# - SortieMatiere / RetourMatiere : les mouvements réels de matières
# - EtapeProduction : le suivi physique de la fabrication (captage,
#   traitement, soufflage, embouteillage, étiquetage, conditionnement)
# - PerteProduction : pertes et rebuts

# Règle importante : le Responsable Production "ne saisit jamais la
# valeur financière des matières" -> aucun champ de prix/coût dans ce
# module (les coûts sont calculés à part, voir apps/couts).
# """

# from django.db import models
# from apps.comptes.models import Utilisateur
# from apps.referentiel.models import Article
# from apps.core.models import generer_numero


# class Priorite(models.TextChoices):
#     BASSE = "BASSE", "Basse"
#     NORMALE = "NORMALE", "Normale"
#     HAUTE = "HAUTE", "Haute"
#     URGENTE = "URGENTE", "Urgente"


# class StatutPlanProduction(models.TextChoices):
#     PREVU = "PREVU", "Prévu"
#     EN_COURS = "EN_COURS", "En cours"
#     REALISE = "REALISE", "Réalisé"
#     ANNULE = "ANNULE", "Annulé"


# class PlanProduction(models.Model):
#     """Ce qu'on prévoit de produire, avant de lancer les OF (§8.2)."""
#     article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
#     date_prevue = models.DateField("Date prévue")
#     quantite_prevue = models.DecimalField("Quantité prévue", max_digits=12, decimal_places=3)
#     priorite = models.CharField("Priorité", max_length=10, choices=Priorite.choices, default=Priorite.NORMALE)
#     statut = models.CharField(
#         "Statut", max_length=20, choices=StatutPlanProduction.choices,
#         default=StatutPlanProduction.PREVU,
#     )
#     cree_par = models.ForeignKey(Utilisateur, verbose_name="Créé par", on_delete=models.PROTECT)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Plan de production"
#         verbose_name_plural = "Plans de production"
#         ordering = ["date_prevue"]

#     def __str__(self):
#         return f"Plan {self.article.code} - {self.date_prevue} ({self.quantite_prevue})"


# class StatutOF(models.TextChoices):
#     """
#     Workflow exact décrit au §8.3 du cahier des charges.
#     Chaque transition ne peut se faire que dans cet ordre
#     (voir OrdreFabrication.passer_statut_suivant()).
#     """
#     BROUILLON = "BROUILLON", "Brouillon"
#     PLANIFIE = "PLANIFIE", "Planifié"
#     LANCE = "LANCE", "Lancé"
#     EN_PRODUCTION = "EN_PRODUCTION", "En production"
#     TERMINE = "TERMINE", "Terminé"
#     CONTROLE_QUALITE = "CONTROLE_QUALITE", "Contrôle qualité"
#     LIBERE = "LIBERE", "Libéré"
#     CLOTURE = "CLOTURE", "Clôturé"


# # Ordre officiel du workflow - utilisé pour vérifier qu'on ne saute pas d'étape
# ORDRE_STATUTS_OF = [
#     StatutOF.BROUILLON, StatutOF.PLANIFIE, StatutOF.LANCE,
#     StatutOF.EN_PRODUCTION, StatutOF.TERMINE, StatutOF.CONTROLE_QUALITE,
#     StatutOF.LIBERE, StatutOF.CLOTURE,
# ]


# class OrdreFabrication(models.Model):
#     """
#     L'Ordre de Fabrication (OF) : le document central de la production.
#     Son numéro est unique et automatique. Son statut ne peut avancer
#     que dans le sens du workflow officiel (ORDRE_STATUTS_OF).
#     """
#     numero = models.CharField("Numéro OF", max_length=30, unique=True, editable=False)
#     plan_production = models.ForeignKey(
#         PlanProduction, verbose_name="Plan de production", on_delete=models.SET_NULL,
#         null=True, blank=True, related_name="ordres_fabrication",
#     )
#     article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
#     quantite_a_produire = models.DecimalField("Quantité à produire", max_digits=12, decimal_places=3)
#     statut = models.CharField(
#         "Statut", max_length=20, choices=StatutOF.choices, default=StatutOF.BROUILLON
#     )
#     responsable = models.ForeignKey(
#         Utilisateur, verbose_name="Responsable Production", on_delete=models.PROTECT,
#         related_name="ordres_fabrication_geres",
#     )
#     agents_affectes = models.ManyToManyField(
#         Utilisateur, verbose_name="Agents Production affectés", blank=True,
#         related_name="ordres_fabrication_affectes",
#         help_text="Agents Production autorisés à intervenir sur cet OF. "
#                    "Un Agent Production ne voit et ne modifie que les OF "
#                    "où il figure ici (règle du cahier des charges : "
#                    "'accès limité aux OF affectés').",
#     )
#     date_lancement = models.DateTimeField("Date de lancement", null=True, blank=True)
#     date_fin = models.DateTimeField("Date de fin", null=True, blank=True)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Ordre de fabrication"
#         verbose_name_plural = "Ordres de fabrication"
#         ordering = ["-date_creation"]

#     def __str__(self):
#         return f"{self.numero} - {self.article.code} ({self.get_statut_display()})"

#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("OF")
#         super().save(*args, **kwargs)

#     def passer_statut_suivant(self):
#         """
#         Fait avancer l'OF d'une étape dans le workflow officiel.
#         Lève une erreur si l'OF est déjà à la dernière étape.

#         Au passage à LANCE, calcule automatiquement les besoins
#         matières théoriques à partir de la fiche technique validée
#         de l'article (règle §8.4 du cahier des charges).
#         """
#         index_actuel = ORDRE_STATUTS_OF.index(self.statut)
#         if index_actuel == len(ORDRE_STATUTS_OF) - 1:
#             raise ValueError("L'OF est déjà clôturé, il n'y a pas d'étape suivante.")

#         nouveau_statut = ORDRE_STATUTS_OF[index_actuel + 1]

#         if nouveau_statut == StatutOF.LANCE:
#             self._calculer_besoins_matieres()
#             from django.utils import timezone
#             self.date_lancement = timezone.now()

#         if nouveau_statut == StatutOF.CLOTURE:
#             from django.utils import timezone
#             self.date_fin = timezone.now()

#         self.statut = nouveau_statut
#         self.save()
#         return self.statut

#     def _calculer_besoins_matieres(self):
#         """
#         Calcule le besoin théorique de chaque matière en multipliant
#         la quantité à produire par la composition de la fiche
#         technique validée la plus récente de l'article (§8.4).
#         """
#         fiche = (
#             self.article.fiches_techniques
#             .filter(statut="VALIDEE")
#             .order_by("-version")
#             .first()
#         )
#         if fiche is None:
#             raise ValueError(
#                 f"Aucune fiche technique validée pour {self.article.code}. "
#                 "Impossible de lancer l'OF."
#             )
#         for ligne in fiche.composition.all():
#             BesoinMatierePrevu.objects.update_or_create(
#                 ordre_fabrication=self,
#                 matiere=ligne.matiere,
#                 defaults={
#                     "quantite_theorique": ligne.quantite_necessaire * self.quantite_a_produire
#                 },
#             )


# class BesoinMatierePrevu(models.Model):
#     """
#     Le besoin théorique en matière pour un OF, calculé automatiquement
#     (voir OrdreFabrication._calculer_besoins_matieres). Sert de
#     référence pour détecter un dépassement lors des sorties matières.
#     """
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.CASCADE, related_name="besoins_matieres",
#     )
#     matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
#     quantite_theorique = models.DecimalField("Quantité théorique nécessaire", max_digits=14, decimal_places=4)

#     class Meta:
#         verbose_name = "Besoin matière prévu"
#         verbose_name_plural = "Besoins matières prévus"
#         unique_together = ("ordre_fabrication", "matiere")

#     def __str__(self):
#         return f"{self.ordre_fabrication.numero} : {self.quantite_theorique} de {self.matiere.designation}"


# class TypeSortie(models.TextChoices):
#     NORMALE = "NORMALE", "Normale"
#     COMPLEMENTAIRE = "COMPLEMENTAIRE", "Complémentaire (dépassement)"


# class SortieMatiere(models.Model):
#     """
#     Une sortie physique de matière pour un OF. Une sortie
#     COMPLEMENTAIRE (au-delà du besoin théorique) exige un motif
#     obligatoire ET une validation du Responsable Production (§8.7).
#     """
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="sorties_matieres",
#     )
#     matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
#     quantite_sortie = models.DecimalField("Quantité sortie", max_digits=14, decimal_places=4)
#     type_sortie = models.CharField(
#         "Type de sortie", max_length=20, choices=TypeSortie.choices,
#         default=TypeSortie.NORMALE,
#     )
#     motif = models.TextField(
#         "Motif", blank=True,
#         help_text="Obligatoire si la sortie est de type Complémentaire.",
#     )
#     valide_par = models.ForeignKey(
#         Utilisateur, verbose_name="Validé par", on_delete=models.PROTECT,
#         null=True, blank=True,
#         help_text="Rempli uniquement pour les sorties complémentaires "
#                    "(validation du Responsable Production, §8.7).",
#     )
#     date_sortie = models.DateTimeField("Date de sortie", auto_now_add=True)

#     class Meta:
#         verbose_name = "Sortie matière"
#         verbose_name_plural = "Sorties matières"
#         ordering = ["-date_sortie"]

#     def __str__(self):
#         return f"Sortie {self.quantite_sortie} {self.matiere.code} pour {self.ordre_fabrication.numero}"

#     def clean(self):
#         from django.core.exceptions import ValidationError
#         if self.type_sortie == TypeSortie.COMPLEMENTAIRE and not self.motif:
#             raise ValidationError(
#                 "Le motif est obligatoire pour une sortie complémentaire."
#             )


# class RetourMatiere(models.Model):
#     """Matière non utilisée, retournée en stock. Consommation nette = Sorties - Retours (§8.8)."""
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="retours_matieres",
#     )
#     matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
#     quantite_retournee = models.DecimalField("Quantité retournée", max_digits=14, decimal_places=4)
#     date_retour = models.DateTimeField("Date de retour", auto_now_add=True)

#     class Meta:
#         verbose_name = "Retour matière"
#         verbose_name_plural = "Retours matières"

#     def __str__(self):
#         return f"Retour {self.quantite_retournee} {self.matiere.code} de {self.ordre_fabrication.numero}"


# class Etape(models.TextChoices):
#     CAPTAGE = "CAPTAGE", "Captage"
#     TRAITEMENT = "TRAITEMENT", "Traitement"
#     SOUFFLAGE = "SOUFFLAGE", "Soufflage"
#     EMBOUTEILLAGE = "EMBOUTEILLAGE", "Embouteillage"
#     ETIQUETAGE = "ETIQUETAGE", "Étiquetage"
#     CONDITIONNEMENT = "CONDITIONNEMENT", "Conditionnement"


# class EtapeProduction(models.Model):
#     """Suivi de la production étape par étape (§8.9)."""
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.CASCADE, related_name="etapes",
#     )
#     etape = models.CharField("Étape", max_length=20, choices=Etape.choices)
#     agent = models.ForeignKey(Utilisateur, verbose_name="Agent Production", on_delete=models.PROTECT)
#     quantite_produite = models.DecimalField(
#         "Quantité produite à cette étape", max_digits=12, decimal_places=3,
#         null=True, blank=True,
#     )
#     date_debut = models.DateTimeField("Début", null=True, blank=True)
#     date_fin = models.DateTimeField("Fin", null=True, blank=True)
#     observations = models.TextField("Observations", blank=True)

#     class Meta:
#         verbose_name = "Étape de production"
#         verbose_name_plural = "Étapes de production"
#         ordering = ["ordre_fabrication", "date_debut"]

#     def __str__(self):
#         return f"{self.ordre_fabrication.numero} - {self.get_etape_display()}"


# class MotifPerte(models.TextChoices):
#     CASSE = "CASSE", "Casse"
#     NON_CONFORMITE = "NON_CONFORMITE", "Non-conformité"
#     PANNE_MACHINE = "PANNE_MACHINE", "Panne machine"
#     ERREUR_MANIPULATION = "ERREUR_MANIPULATION", "Erreur de manipulation"
#     AUTRE = "AUTRE", "Autre"


# class PerteProduction(models.Model):
#     """Pertes et rebuts constatés en cours de production (§8.10)."""
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="pertes",
#     )
#     etape = models.ForeignKey(
#         EtapeProduction, verbose_name="Étape concernée", on_delete=models.SET_NULL,
#         null=True, blank=True,
#     )
#     quantite_perte = models.DecimalField("Quantité perdue", max_digits=12, decimal_places=3)
#     motif = models.CharField("Motif", max_length=30, choices=MotifPerte.choices)
#     observations = models.TextField("Observations", blank=True)
#     date_constat = models.DateTimeField("Date du constat", auto_now_add=True)

#     class Meta:
#         verbose_name = "Perte de production"
#         verbose_name_plural = "Pertes de production"

#     def __str__(self):
#         return f"Perte {self.quantite_perte} sur {self.ordre_fabrication.numero} ({self.get_motif_display()})"



"""
Module 2 - Production (cahier des charges mis à jour, §5).

Le cœur métier de l'application. Contient :
- PlanProduction : la prévision (§5.3), convertible en OF
- OrdreFabrication (OF) : l'exécution réelle, workflow de statuts §5.4.2
- BesoinMatierePrevu : calculé AUTOMATIQUEMENT dès la CRÉATION de l'OF
  (§5.5 : "Lorsque l'OF est créé, le logiciel doit automatiquement lire
  la fiche technique") - pas à une transition de statut ultérieure,
  contrairement à une version antérieure de ce module.
- DemandeMatiere : la demande du responsable production au magasin (§5.6)
- DemandeComplementaire : demande de matière supplémentaire en cours de
  production, distincte de la demande initiale (§5.7)
- SortieMatiere / RetourMatiere : les mouvements réels de matières
- SuiviProduction : le suivi général d'une session de production (§5.8)
- SuiviEau : le suivi spécifique de l'eau, volumes et écarts par étape (§5.9)
- EtapeProduction : le suivi par étape du processus de fabrication
- PerteProduction : pertes et rebuts (§5.11)

Règle importante : le Responsable Production "ne saisit jamais la
valeur financière des matières" -> aucun champ de prix/coût dans ce
module (les coûts sont calculés à part, voir apps/couts).

Règle de verrouillage (§5.14.4) : "Une fois clôturé, l'OF ne doit plus
être modifiable librement." Voir OrdreFabrication.est_verrouille,
utilisé par les modèles dépendants (SortieMatiere, RetourMatiere...)
pour refuser toute nouvelle écriture une fois l'OF CLOTURE ou ANNULE.
"""

from django.db import models
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero


class Priorite(models.TextChoices):
    BASSE = "BASSE", "Basse"
    NORMALE = "NORMALE", "Normale"
    HAUTE = "HAUTE", "Haute"
    URGENTE = "URGENTE", "Urgente"


class StatutPlanProduction(models.TextChoices):
    """
    Le document précise que la prévision "ne doit pas obligatoirement
    créer immédiatement une sortie de stock. Elle sert surtout à
    préparer l'activité" (§5.3) - PREVISION est donc le statut de
    départ, distinct d'un OF réel.
    """
    PREVISION = "PREVISION", "Prévision"
    A_CONVERTIR_EN_OF = "A_CONVERTIR_EN_OF", "À convertir en OF"
    CONVERTIE = "CONVERTIE", "Convertie en OF"
    ANNULEE = "ANNULEE", "Annulée"


class PlanProduction(models.Model):
    """Le programme / prévision de production (§5.3), avant conversion en OF."""
    article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
    date_prevue = models.DateField("Date prévue")
    quantite_prevue = models.DecimalField("Quantité prévue", max_digits=12, decimal_places=3)
    priorite = models.CharField("Priorité", max_length=10, choices=Priorite.choices, default=Priorite.NORMALE)
    commentaire = models.TextField("Commentaire", blank=True)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutPlanProduction.choices,
        default=StatutPlanProduction.PREVISION,
    )
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Créé par", on_delete=models.PROTECT)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Plan de production"
        verbose_name_plural = "Plans de production"
        ordering = ["date_prevue"]

    def __str__(self):
        return f"Plan {self.article.code} - {self.date_prevue} ({self.quantite_prevue})"

    def convertir_en_of(self, responsable):
        """
        Transforme la prévision en Ordre de Fabrication réel (§5.3 :
        "Le responsable pourra ensuite convertir la prévision en OF").
        Crée l'OF (ce qui déclenche automatiquement le calcul des
        besoins matières, voir OrdreFabrication.save()) et marque la
        prévision comme convertie.
        """
        if self.statut == StatutPlanProduction.CONVERTIE:
            raise ValueError("Cette prévision a déjà été convertie en OF.")
        of = OrdreFabrication.objects.create(
            plan_production=self, article=self.article,
            quantite_a_produire=self.quantite_prevue, responsable=responsable,
        )
        self.statut = StatutPlanProduction.CONVERTIE
        self.save()
        return of


class StatutOF(models.TextChoices):
    """
    Workflow exact décrit au §5.4.2 du cahier des charges mis à jour.
    ANNULE est une branche possible depuis n'importe quel statut avant
    CLOTURE (voir OrdreFabrication.annuler()), pas une étape de la
    séquence normale ORDRE_STATUTS_OF.
    """
    BROUILLON = "BROUILLON", "Brouillon"
    A_PREPARER = "A_PREPARER", "À préparer"
    MATIERES_EN_PREPARATION = "MATIERES_EN_PREPARATION", "Matières en préparation"
    PRET = "PRET", "Prêt"
    EN_PRODUCTION = "EN_PRODUCTION", "En production"
    PRODUCTION_TERMINEE = "PRODUCTION_TERMINEE", "Production terminée"
    EN_CONTROLE = "EN_CONTROLE", "En contrôle"
    CLOTURE = "CLOTURE", "Clôturé"
    ANNULE = "ANNULE", "Annulé"


# Ordre officiel du workflow normal (hors ANNULE, qui est une branche à part)
ORDRE_STATUTS_OF = [
    StatutOF.BROUILLON, StatutOF.A_PREPARER, StatutOF.MATIERES_EN_PREPARATION,
    StatutOF.PRET, StatutOF.EN_PRODUCTION, StatutOF.PRODUCTION_TERMINEE,
    StatutOF.EN_CONTROLE, StatutOF.CLOTURE,
]


class OrdreFabrication(models.Model):
    """
    L'Ordre de Fabrication (OF) : le document central de la production.
    Son numéro est unique et automatique (§5.4.1). Son statut ne peut
    avancer que dans le sens du workflow officiel (ORDRE_STATUTS_OF),
    sauf annulation qui est une branche à part.
    """
    numero = models.CharField("Numéro OF", max_length=30, unique=True, editable=False)
    plan_production = models.ForeignKey(
        PlanProduction, verbose_name="Plan de production", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="ordres_fabrication",
    )
    article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
    quantite_a_produire = models.DecimalField("Quantité à produire", max_digits=12, decimal_places=3)
    equipe = models.CharField("Équipe", max_length=100, blank=True)
    statut = models.CharField(
        "Statut", max_length=30, choices=StatutOF.choices, default=StatutOF.BROUILLON
    )
    motif_annulation = models.TextField(
        "Motif d'annulation", blank=True,
        help_text="Renseigné uniquement si l'OF est annulé (§5.4.2).",
    )
    responsable = models.ForeignKey(
        Utilisateur, verbose_name="Responsable Production", on_delete=models.PROTECT,
        related_name="ordres_fabrication_geres",
    )
    agents_affectes = models.ManyToManyField(
        Utilisateur, verbose_name="Agents Production affectés", blank=True,
        related_name="ordres_fabrication_affectes",
        help_text="Agents Production autorisés à intervenir sur cet OF. "
                   "Un Agent Production ne voit et ne modifie que les OF "
                   "où il figure ici (règle du cahier des charges : "
                   "'accès limité aux OF affectés').",
    )
    date_debut_production = models.DateTimeField(
        "Date de début de production", null=True, blank=True,
        help_text="Renseignée automatiquement au passage à 'En production'.",
    )
    date_fin = models.DateTimeField("Date de clôture", null=True, blank=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Ordre de fabrication"
        verbose_name_plural = "Ordres de fabrication"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero} - {self.article.code} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        """
        Génère le numéro automatique, puis calcule les besoins
        matières AUTOMATIQUEMENT si c'est une CRÉATION (§5.5 : le
        calcul se fait dès la création de l'OF, pas à une transition
        de statut ultérieure).
        """
        creation = self._state.adding
        if not self.numero:
            self.numero = generer_numero("OF")
        super().save(*args, **kwargs)
        if creation:
            self._calculer_besoins_matieres()

    @property
    def est_verrouille(self):
        """
        §5.14.4 : "Une fois clôturé, l'OF ne doit plus être modifiable
        librement." Un OF annulé est également figé. Utilisé par les
        modèles dépendants pour refuser toute nouvelle écriture.
        """
        return self.statut in (StatutOF.CLOTURE, StatutOF.ANNULE)

    def passer_statut_suivant(self):
        """Fait avancer l'OF d'une étape dans le workflow officiel."""
        if self.est_verrouille:
            raise ValueError(f"L'OF est {self.get_statut_display().lower()}, son statut ne peut plus changer.")

        index_actuel = ORDRE_STATUTS_OF.index(self.statut)
        if index_actuel == len(ORDRE_STATUTS_OF) - 1:
            raise ValueError("L'OF est déjà clôturé, il n'y a pas d'étape suivante.")

        nouveau_statut = ORDRE_STATUTS_OF[index_actuel + 1]
        from django.utils import timezone

        if nouveau_statut == StatutOF.EN_PRODUCTION:
            self.date_debut_production = timezone.now()
        if nouveau_statut == StatutOF.CLOTURE:
            self.date_fin = timezone.now()

        self.statut = nouveau_statut
        self.save()
        return self.statut

    def annuler(self, motif):
        """
        Annule l'OF avec un motif obligatoire. Impossible si déjà
        clôturé (§5.4.2 : Clôturé est un état final, Annulé en est un autre).
        """
        if self.statut == StatutOF.CLOTURE:
            raise ValueError("Un OF déjà clôturé ne peut plus être annulé.")
        if not motif:
            raise ValueError("Le motif d'annulation est obligatoire.")
        self.statut = StatutOF.ANNULE
        self.motif_annulation = motif
        self.save()

    def _calculer_besoins_matieres(self):
        """
        Calcule le besoin théorique de chaque matière en multipliant
        la quantité à produire par la composition de la fiche
        technique validée la plus récente de l'article (§5.5).

        Si aucune fiche technique validée n'existe, ne bloque PAS la
        création de l'OF (un OF peut exister brièvement le temps de
        régulariser la fiche technique) mais ne crée aucun besoin :
        le tableau de bord (voir vues) le signalera comme anomalie.
        """
        fiche = (
            self.article.fiches_techniques
            .filter(statut="VALIDEE")
            .order_by("-version")
            .first()
        )
        if fiche is None:
            return
        for ligne in fiche.composition.all():
            BesoinMatierePrevu.objects.update_or_create(
                ordre_fabrication=self,
                matiere=ligne.matiere,
                defaults={
                    "quantite_theorique": ligne.quantite_necessaire * self.quantite_a_produire
                },
            )

    def calculer_consommation_reelle(self):
        """
        §5.10 : Consommation réelle = Sorties initiales + Sorties
        complémentaires - Retours magasin. Compare au besoin théorique
        et calcule l'écart, matière par matière.

        Retourne une liste de dicts, un par matière ayant eu au moins
        un mouvement ou un besoin théorique.
        """
        from django.db.models import Sum

        matieres_ids = set(
            self.besoins_matieres.values_list("matiere_id", flat=True)
        ) | set(
            self.sorties_matieres.values_list("matiere_id", flat=True)
        )

        resultat = []
        for matiere_id in matieres_ids:
            matiere = Article.objects.get(pk=matiere_id)
            theorique = (
                self.besoins_matieres.filter(matiere_id=matiere_id)
                .aggregate(total=Sum("quantite_theorique"))["total"] or 0
            )
            sorties = (
                self.sorties_matieres.filter(matiere_id=matiere_id)
                .aggregate(total=Sum("quantite_sortie"))["total"] or 0
            )
            retours = (
                self.retours_matieres.filter(matiere_id=matiere_id)
                .aggregate(total=Sum("quantite_retournee"))["total"] or 0
            )
            reelle = sorties - retours
            ecart = reelle - theorique
            ecart_pourcentage = (ecart / theorique * 100) if theorique else None

            resultat.append({
                "matiere": matiere.code,
                "matiere_designation": matiere.designation,
                "theorique": theorique,
                "reelle": reelle,
                "ecart": ecart,
                "ecart_pourcentage": ecart_pourcentage,
            })
        return resultat


class BesoinMatierePrevu(models.Model):
    """
    Le besoin théorique en matière pour un OF, calculé automatiquement
    à la création de l'OF (voir OrdreFabrication._calculer_besoins_matieres).
    """
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.CASCADE, related_name="besoins_matieres",
    )
    matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    quantite_theorique = models.DecimalField("Quantité théorique nécessaire", max_digits=14, decimal_places=4)

    class Meta:
        verbose_name = "Besoin matière prévu"
        verbose_name_plural = "Besoins matières prévus"
        unique_together = ("ordre_fabrication", "matiere")

    def __str__(self):
        return f"{self.ordre_fabrication.numero} : {self.quantite_theorique} de {self.matiere.designation}"

    def stock_disponible(self):
        """Somme du stock disponible de cette matière tous dépôts confondus (§5.5, colonne 'Stock disponible')."""
        from apps.stocks.models import StockArticle
        from django.db.models import Sum, F
        agg = StockArticle.objects.filter(article=self.matiere).aggregate(
            total=Sum(F("quantite_physique") - F("quantite_bloquee") - F("quantite_reservee"))
        )
        return agg["total"] or 0

    def manquant(self):
        """§5.5, colonne 'Manquant' : partie du besoin non couverte par le stock disponible."""
        manque = self.quantite_theorique - self.stock_disponible()
        return manque if manque > 0 else 0

    def situation(self):
        """§5.5, colonne 'Situation' : Disponible / Insuffisant."""
        return "Insuffisant" if self.manquant() > 0 else "Disponible"


class StatutDemandeMatiere(models.TextChoices):
    A_PREPARER = "A_PREPARER", "À préparer"
    PARTIELLEMENT_PREPAREE = "PARTIELLEMENT_PREPAREE", "Partiellement préparée"
    PREPAREE = "PREPAREE", "Préparée"
    LIVREE_A_LA_PRODUCTION = "LIVREE_A_LA_PRODUCTION", "Livrée à la production"
    ANNULEE = "ANNULEE", "Annulée"


class DemandeMatiere(models.Model):
    """
    §5.6 : la demande du Responsable Production au magasin pour les
    matières nécessaires à un OF. Distincte du besoin théorique
    (calculé automatiquement) : c'est ici l'acte de DEMANDER
    concrètement au magasinier de préparer et sortir la matière.
    """
    numero = models.CharField("N° demande", max_length=30, unique=True, editable=False)
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="demandes_matieres",
    )
    matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    quantite_demandee = models.DecimalField("Quantité demandée", max_digits=14, decimal_places=3)
    demandeur = models.ForeignKey(Utilisateur, verbose_name="Demandeur", on_delete=models.PROTECT)
    statut = models.CharField(
        "Statut", max_length=25, choices=StatutDemandeMatiere.choices,
        default=StatutDemandeMatiere.A_PREPARER,
    )
    date_creation = models.DateTimeField("Date", auto_now_add=True)

    class Meta:
        verbose_name = "Demande de matière"
        verbose_name_plural = "Demandes de matières"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero} - {self.matiere.code} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("DM")
        super().save(*args, **kwargs)

    def livrer_a_production(self, quantite_livree=None):
        """
        Le Magasinier livre la matière : génère automatiquement la
        SortieMatiere correspondante (pas de ressaisie, §15 du cahier
        des charges) et met à jour le statut de la demande.
        """
        if self.ordre_fabrication.est_verrouille:
            raise ValueError("Cet OF est clôturé ou annulé, impossible de livrer une matière.")
        quantite_livree = quantite_livree if quantite_livree is not None else self.quantite_demandee
        SortieMatiere.objects.create(
            ordre_fabrication=self.ordre_fabrication, matiere=self.matiere,
            quantite_sortie=quantite_livree, type_sortie=TypeSortie.NORMALE,
        )
        self.statut = (
            StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION
            if quantite_livree >= self.quantite_demandee
            else StatutDemandeMatiere.PARTIELLEMENT_PREPAREE
        )
        self.save()


class StatutDemandeComplementaire(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    APPROUVEE_ET_LIVREE = "APPROUVEE_ET_LIVREE", "Approuvée et livrée"
    REJETEE = "REJETEE", "Rejetée"


class DemandeComplementaire(models.Model):
    """
    §5.7 : pendant la production, une demande de matière supplémentaire,
    avec motif obligatoire ("bouton Demander un complément"). Distincte
    de DemandeMatiere (la demande initiale). Son approbation génère
    automatiquement la SortieMatiere COMPLEMENTAIRE correspondante.
    """
    numero = models.CharField("N° complément", max_length=30, unique=True, editable=False)
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="demandes_complementaires",
    )
    matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
    motif = models.TextField("Motif", help_text="Obligatoire (ex : 'Défauts au soufflage').")
    demandeur = models.ForeignKey(Utilisateur, verbose_name="Demandeur", on_delete=models.PROTECT)
    statut = models.CharField(
        "Statut", max_length=25, choices=StatutDemandeComplementaire.choices,
        default=StatutDemandeComplementaire.EN_ATTENTE,
    )
    date_creation = models.DateTimeField("Date", auto_now_add=True)

    class Meta:
        verbose_name = "Demande complémentaire"
        verbose_name_plural = "Demandes complémentaires"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero} - {self.matiere.code} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("DC")
        super().save(*args, **kwargs)

    def approuver_et_livrer(self, utilisateur):
        """Le Magasinier (ou Responsable Production) approuve : génère la SortieMatiere COMPLEMENTAIRE automatiquement."""
        if self.ordre_fabrication.est_verrouille:
            raise ValueError("Cet OF est clôturé ou annulé, impossible de livrer un complément.")
        SortieMatiere.objects.create(
            ordre_fabrication=self.ordre_fabrication, matiere=self.matiere,
            quantite_sortie=self.quantite, type_sortie=TypeSortie.COMPLEMENTAIRE,
            motif=self.motif, valide_par=utilisateur,
        )
        self.statut = StatutDemandeComplementaire.APPROUVEE_ET_LIVREE
        self.save()

    def rejeter(self):
        self.statut = StatutDemandeComplementaire.REJETEE
        self.save()


class TypeSortie(models.TextChoices):
    NORMALE = "NORMALE", "Normale"
    COMPLEMENTAIRE = "COMPLEMENTAIRE", "Complémentaire (dépassement)"


class SortieMatiere(models.Model):
    """
    Une sortie physique de matière pour un OF. Une sortie
    COMPLEMENTAIRE exige un motif obligatoire ET une validation
    (normalement via DemandeComplementaire.approuver_et_livrer, qui
    remplit motif/valide_par automatiquement).
    """
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="sorties_matieres",
    )
    matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    quantite_sortie = models.DecimalField("Quantité sortie", max_digits=14, decimal_places=4)
    type_sortie = models.CharField(
        "Type de sortie", max_length=20, choices=TypeSortie.choices,
        default=TypeSortie.NORMALE,
    )
    motif = models.TextField(
        "Motif", blank=True,
        help_text="Obligatoire si la sortie est de type Complémentaire.",
    )
    valide_par = models.ForeignKey(
        Utilisateur, verbose_name="Validé par", on_delete=models.PROTECT,
        null=True, blank=True,
        help_text="Rempli uniquement pour les sorties complémentaires.",
    )
    date_sortie = models.DateTimeField("Date de sortie", auto_now_add=True)

    class Meta:
        verbose_name = "Sortie matière"
        verbose_name_plural = "Sorties matières"
        ordering = ["-date_sortie"]

    def __str__(self):
        return f"Sortie {self.quantite_sortie} {self.matiere.code} pour {self.ordre_fabrication.numero}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.type_sortie == TypeSortie.COMPLEMENTAIRE and not self.motif:
            raise ValidationError(
                "Le motif est obligatoire pour une sortie complémentaire."
            )
        if self.ordre_fabrication_id and self.ordre_fabrication.est_verrouille:
            raise ValidationError(
                "Cet OF est clôturé ou annulé : plus aucune sortie matière n'est possible."
            )


class RetourMatiere(models.Model):
    """Matière non utilisée, retournée en stock. Consommation nette = Sorties - Retours (§5.10)."""
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="retours_matieres",
    )
    matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    quantite_retournee = models.DecimalField("Quantité retournée", max_digits=14, decimal_places=4)
    motif = models.CharField("Motif", max_length=200, blank=True)
    date_retour = models.DateTimeField("Date de retour", auto_now_add=True)

    class Meta:
        verbose_name = "Retour matière"
        verbose_name_plural = "Retours matières"

    def __str__(self):
        return f"Retour {self.quantite_retournee} {self.matiere.code} de {self.ordre_fabrication.numero}"


class SuiviProduction(models.Model):
    """
    §5.8 : ce qui se passe réellement sur la ligne, saisi par
    session/journée. Distinct du suivi par étape (EtapeProduction,
    plus fin, captage/traitement/etc.) : ceci est la synthèse d'une
    plage horaire de production.
    """
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.CASCADE, related_name="suivis_production",
    )
    date = models.DateField("Date")
    heure_debut = models.TimeField("Heure de début")
    heure_fin = models.TimeField("Heure de fin", null=True, blank=True)
    equipe = models.CharField("Équipe", max_length=100, blank=True)
    quantite_entree = models.DecimalField("Quantité entrée", max_digits=12, decimal_places=3)
    quantite_produite = models.DecimalField("Quantité produite", max_digits=12, decimal_places=3, null=True, blank=True)
    quantite_conforme = models.DecimalField("Quantité conforme", max_digits=12, decimal_places=3, null=True, blank=True)
    quantite_rejetee = models.DecimalField("Quantité rejetée", max_digits=12, decimal_places=3, null=True, blank=True)
    arrets = models.TextField("Arrêts", blank=True, help_text="Ex : 'Arrêt 15 min réglage'")
    incidents = models.TextField("Incidents", blank=True)
    observations = models.TextField("Observations", blank=True)

    class Meta:
        verbose_name = "Suivi de production"
        verbose_name_plural = "Suivis de production"
        ordering = ["-date", "-heure_debut"]

    def __str__(self):
        return f"{self.ordre_fabrication.numero} - {self.date} {self.heure_debut}"


class SuiviEau(models.Model):
    """
    §5.9 : suivi spécifique de la production d'eau, avec calcul
    automatique des écarts entre chaque étape du flux (captage ->
    traitement -> embouteillage). Un seul enregistrement par OF.
    """
    ordre_fabrication = models.OneToOneField(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.CASCADE, related_name="suivi_eau",
    )
    volume_capte_l = models.DecimalField("Volume capté (L)", max_digits=12, decimal_places=2)
    volume_envoye_traitement_l = models.DecimalField("Volume envoyé au traitement (L)", max_digits=12, decimal_places=2, null=True, blank=True)
    volume_obtenu_traitement_l = models.DecimalField("Volume obtenu après traitement (L)", max_digits=12, decimal_places=2)
    volume_envoye_embouteillage_l = models.DecimalField("Volume envoyé à l'embouteillage (L)", max_digits=12, decimal_places=2)
    bouteilles_produites = models.PositiveIntegerField("Bouteilles produites")
    bouteilles_conformes = models.PositiveIntegerField("Bouteilles conformes")
    bouteilles_rejetees = models.PositiveIntegerField("Bouteilles rejetées", default=0)
    nombre_packs = models.PositiveIntegerField("Nombre de packs", null=True, blank=True)

    class Meta:
        verbose_name = "Suivi de l'eau"
        verbose_name_plural = "Suivis de l'eau"

    def __str__(self):
        return f"Suivi eau - {self.ordre_fabrication.numero}"

    def _taux(self, perte, entree):
        return round(float(perte) / float(entree) * 100, 2) if entree else None

    @property
    def perte_captage_traitement(self):
        return self.volume_capte_l - self.volume_obtenu_traitement_l

    @property
    def taux_perte_captage_traitement(self):
        return self._taux(self.perte_captage_traitement, self.volume_capte_l)

    @property
    def perte_traitement_embouteillage(self):
        return self.volume_obtenu_traitement_l - self.volume_envoye_embouteillage_l

    @property
    def taux_perte_traitement_embouteillage(self):
        return self._taux(self.perte_traitement_embouteillage, self.volume_obtenu_traitement_l)

    @property
    def taux_perte_embouteillage(self):
        return self._taux(self.bouteilles_rejetees, self.bouteilles_produites)


class Etape(models.TextChoices):
    CAPTAGE = "CAPTAGE", "Captage"
    TRAITEMENT = "TRAITEMENT", "Traitement"
    SOUFFLAGE = "SOUFFLAGE", "Soufflage"
    EMBOUTEILLAGE = "EMBOUTEILLAGE", "Embouteillage"
    ETIQUETAGE = "ETIQUETAGE", "Étiquetage"
    CONDITIONNEMENT = "CONDITIONNEMENT", "Conditionnement"


class EtapeProduction(models.Model):
    """Suivi de la production étape par étape (processus de fabrication de la fiche technique)."""
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.CASCADE, related_name="etapes",
    )
    etape = models.CharField("Étape", max_length=20, choices=Etape.choices)
    agent = models.ForeignKey(Utilisateur, verbose_name="Agent Production", on_delete=models.PROTECT)
    quantite_produite = models.DecimalField(
        "Quantité produite à cette étape", max_digits=12, decimal_places=3,
        null=True, blank=True,
    )
    date_debut = models.DateTimeField("Début", null=True, blank=True)
    date_fin = models.DateTimeField("Fin", null=True, blank=True)
    observations = models.TextField("Observations", blank=True)

    class Meta:
        verbose_name = "Étape de production"
        verbose_name_plural = "Étapes de production"
        ordering = ["ordre_fabrication", "date_debut"]

    def __str__(self):
        return f"{self.ordre_fabrication.numero} - {self.get_etape_display()}"


class MotifPerte(models.TextChoices):
    """Causes paramétrables exactes du §5.11 du cahier des charges."""
    CASSE = "CASSE", "Casse"
    MAUVAIS_REGLAGE = "MAUVAIS_REGLAGE", "Mauvais réglage"
    FUITE = "FUITE", "Fuite"
    DEFAUT_MATIERE = "DEFAUT_MATIERE", "Défaut matière"
    DEFAUT_BOUTEILLE = "DEFAUT_BOUTEILLE", "Défaut bouteille"
    CONTROLE_QUALITE = "CONTROLE_QUALITE", "Contrôle qualité"
    ARRET_MACHINE = "ARRET_MACHINE", "Arrêt machine"
    NETTOYAGE = "NETTOYAGE", "Nettoyage"
    ERREUR_OPERATEUR = "ERREUR_OPERATEUR", "Erreur opérateur"
    AUTRE = "AUTRE", "Autre"


class PerteProduction(models.Model):
    """Pertes et rebuts constatés en cours de production (§5.11)."""
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="pertes",
    )
    etape = models.ForeignKey(
        EtapeProduction, verbose_name="Étape concernée", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    quantite_perte = models.DecimalField("Quantité perdue", max_digits=12, decimal_places=3)
    taux_perte = models.DecimalField(
        "Taux de perte (%)", max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Peut être calculé côté client (quantité perdue / quantité entrée) ou saisi directement.",
    )
    motif = models.CharField("Motif", max_length=30, choices=MotifPerte.choices)
    observations = models.TextField("Observations", blank=True)
    date_constat = models.DateTimeField("Date du constat", auto_now_add=True)

    class Meta:
        verbose_name = "Perte de production"
        verbose_name_plural = "Pertes de production"

    def __str__(self):
        return f"Perte {self.quantite_perte} sur {self.ordre_fabrication.numero} ({self.get_motif_display()})"