"""
Module 5 - Production.

Le cœur métier de l'application. Contient :
- PlanProduction : ce qu'on prévoit de fabriquer
- OrdreFabrication (OF) : l'exécution réelle, avec son workflow de
  statuts (§8.3 du cahier des charges)
- BesoinMatierePrevu : calculé AUTOMATIQUEMENT à partir de la fiche
  technique quand un OF est lancé (§8.4)
- SortieMatiere / RetourMatiere : les mouvements réels de matières
- EtapeProduction : le suivi physique de la fabrication (captage,
  traitement, soufflage, embouteillage, étiquetage, conditionnement)
- PerteProduction : pertes et rebuts

Règle importante : le Responsable Production "ne saisit jamais la
valeur financière des matières" -> aucun champ de prix/coût dans ce
module (les coûts sont calculés à part, voir apps/couts).
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
    PREVU = "PREVU", "Prévu"
    EN_COURS = "EN_COURS", "En cours"
    REALISE = "REALISE", "Réalisé"
    ANNULE = "ANNULE", "Annulé"


class PlanProduction(models.Model):
    """Ce qu'on prévoit de produire, avant de lancer les OF (§8.2)."""
    article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
    date_prevue = models.DateField("Date prévue")
    quantite_prevue = models.DecimalField("Quantité prévue", max_digits=12, decimal_places=3)
    priorite = models.CharField("Priorité", max_length=10, choices=Priorite.choices, default=Priorite.NORMALE)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutPlanProduction.choices,
        default=StatutPlanProduction.PREVU,
    )
    cree_par = models.ForeignKey(Utilisateur, verbose_name="Créé par", on_delete=models.PROTECT)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Plan de production"
        verbose_name_plural = "Plans de production"
        ordering = ["date_prevue"]

    def __str__(self):
        return f"Plan {self.article.code} - {self.date_prevue} ({self.quantite_prevue})"


class StatutOF(models.TextChoices):
    """
    Workflow exact décrit au §8.3 du cahier des charges.
    Chaque transition ne peut se faire que dans cet ordre
    (voir OrdreFabrication.passer_statut_suivant()).
    """
    BROUILLON = "BROUILLON", "Brouillon"
    PLANIFIE = "PLANIFIE", "Planifié"
    LANCE = "LANCE", "Lancé"
    EN_PRODUCTION = "EN_PRODUCTION", "En production"
    TERMINE = "TERMINE", "Terminé"
    CONTROLE_QUALITE = "CONTROLE_QUALITE", "Contrôle qualité"
    LIBERE = "LIBERE", "Libéré"
    CLOTURE = "CLOTURE", "Clôturé"


# Ordre officiel du workflow - utilisé pour vérifier qu'on ne saute pas d'étape
ORDRE_STATUTS_OF = [
    StatutOF.BROUILLON, StatutOF.PLANIFIE, StatutOF.LANCE,
    StatutOF.EN_PRODUCTION, StatutOF.TERMINE, StatutOF.CONTROLE_QUALITE,
    StatutOF.LIBERE, StatutOF.CLOTURE,
]


class OrdreFabrication(models.Model):
    """
    L'Ordre de Fabrication (OF) : le document central de la production.
    Son numéro est unique et automatique. Son statut ne peut avancer
    que dans le sens du workflow officiel (ORDRE_STATUTS_OF).
    """
    numero = models.CharField("Numéro OF", max_length=30, unique=True, editable=False)
    plan_production = models.ForeignKey(
        PlanProduction, verbose_name="Plan de production", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="ordres_fabrication",
    )
    article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
    quantite_a_produire = models.DecimalField("Quantité à produire", max_digits=12, decimal_places=3)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutOF.choices, default=StatutOF.BROUILLON
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
    date_lancement = models.DateTimeField("Date de lancement", null=True, blank=True)
    date_fin = models.DateTimeField("Date de fin", null=True, blank=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Ordre de fabrication"
        verbose_name_plural = "Ordres de fabrication"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero} - {self.article.code} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("OF")
        super().save(*args, **kwargs)

    def passer_statut_suivant(self):
        """
        Fait avancer l'OF d'une étape dans le workflow officiel.
        Lève une erreur si l'OF est déjà à la dernière étape.

        Au passage à LANCE, calcule automatiquement les besoins
        matières théoriques à partir de la fiche technique validée
        de l'article (règle §8.4 du cahier des charges).
        """
        index_actuel = ORDRE_STATUTS_OF.index(self.statut)
        if index_actuel == len(ORDRE_STATUTS_OF) - 1:
            raise ValueError("L'OF est déjà clôturé, il n'y a pas d'étape suivante.")

        nouveau_statut = ORDRE_STATUTS_OF[index_actuel + 1]

        if nouveau_statut == StatutOF.LANCE:
            self._calculer_besoins_matieres()
            from django.utils import timezone
            self.date_lancement = timezone.now()

        if nouveau_statut == StatutOF.CLOTURE:
            from django.utils import timezone
            self.date_fin = timezone.now()

        self.statut = nouveau_statut
        self.save()
        return self.statut

    def _calculer_besoins_matieres(self):
        """
        Calcule le besoin théorique de chaque matière en multipliant
        la quantité à produire par la composition de la fiche
        technique validée la plus récente de l'article (§8.4).
        """
        fiche = (
            self.article.fiches_techniques
            .filter(statut="VALIDEE")
            .order_by("-version")
            .first()
        )
        if fiche is None:
            raise ValueError(
                f"Aucune fiche technique validée pour {self.article.code}. "
                "Impossible de lancer l'OF."
            )
        for ligne in fiche.composition.all():
            BesoinMatierePrevu.objects.update_or_create(
                ordre_fabrication=self,
                matiere=ligne.matiere,
                defaults={
                    "quantite_theorique": ligne.quantite_necessaire * self.quantite_a_produire
                },
            )


class BesoinMatierePrevu(models.Model):
    """
    Le besoin théorique en matière pour un OF, calculé automatiquement
    (voir OrdreFabrication._calculer_besoins_matieres). Sert de
    référence pour détecter un dépassement lors des sorties matières.
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


class TypeSortie(models.TextChoices):
    NORMALE = "NORMALE", "Normale"
    COMPLEMENTAIRE = "COMPLEMENTAIRE", "Complémentaire (dépassement)"


class SortieMatiere(models.Model):
    """
    Une sortie physique de matière pour un OF. Une sortie
    COMPLEMENTAIRE (au-delà du besoin théorique) exige un motif
    obligatoire ET une validation du Responsable Production (§8.7).
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
        help_text="Rempli uniquement pour les sorties complémentaires "
                   "(validation du Responsable Production, §8.7).",
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


class RetourMatiere(models.Model):
    """Matière non utilisée, retournée en stock. Consommation nette = Sorties - Retours (§8.8)."""
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="retours_matieres",
    )
    matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    quantite_retournee = models.DecimalField("Quantité retournée", max_digits=14, decimal_places=4)
    date_retour = models.DateTimeField("Date de retour", auto_now_add=True)

    class Meta:
        verbose_name = "Retour matière"
        verbose_name_plural = "Retours matières"

    def __str__(self):
        return f"Retour {self.quantite_retournee} {self.matiere.code} de {self.ordre_fabrication.numero}"


class Etape(models.TextChoices):
    CAPTAGE = "CAPTAGE", "Captage"
    TRAITEMENT = "TRAITEMENT", "Traitement"
    SOUFFLAGE = "SOUFFLAGE", "Soufflage"
    EMBOUTEILLAGE = "EMBOUTEILLAGE", "Embouteillage"
    ETIQUETAGE = "ETIQUETAGE", "Étiquetage"
    CONDITIONNEMENT = "CONDITIONNEMENT", "Conditionnement"


class EtapeProduction(models.Model):
    """Suivi de la production étape par étape (§8.9)."""
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
    CASSE = "CASSE", "Casse"
    NON_CONFORMITE = "NON_CONFORMITE", "Non-conformité"
    PANNE_MACHINE = "PANNE_MACHINE", "Panne machine"
    ERREUR_MANIPULATION = "ERREUR_MANIPULATION", "Erreur de manipulation"
    AUTRE = "AUTRE", "Autre"


class PerteProduction(models.Model):
    """Pertes et rebuts constatés en cours de production (§8.10)."""
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="pertes",
    )
    etape = models.ForeignKey(
        EtapeProduction, verbose_name="Étape concernée", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    quantite_perte = models.DecimalField("Quantité perdue", max_digits=12, decimal_places=3)
    motif = models.CharField("Motif", max_length=30, choices=MotifPerte.choices)
    observations = models.TextField("Observations", blank=True)
    date_constat = models.DateTimeField("Date du constat", auto_now_add=True)

    class Meta:
        verbose_name = "Perte de production"
        verbose_name_plural = "Pertes de production"

    def __str__(self):
        return f"Perte {self.quantite_perte} sur {self.ordre_fabrication.numero} ({self.get_motif_display()})"
