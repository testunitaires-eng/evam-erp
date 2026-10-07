

# """
# Module 2 - Production (cahier des charges mis à jour, §5).

# Le cœur métier de l'application. Contient :
# - PlanProduction : la prévision (§5.3), convertible en OF
# - OrdreFabrication (OF) : l'exécution réelle, workflow de statuts §5.4.2
# - BesoinMatierePrevu : calculé AUTOMATIQUEMENT dès la CRÉATION de l'OF
#   (§5.5 : "Lorsque l'OF est créé, le logiciel doit automatiquement lire
#   la fiche technique") - pas à une transition de statut ultérieure,
#   contrairement à une version antérieure de ce module.
# - DemandeMatiere : la demande du responsable production au magasin (§5.6)
# - DemandeComplementaire : demande de matière supplémentaire en cours de
#   production, distincte de la demande initiale (§5.7)
# - SortieMatiere / RetourMatiere : les mouvements réels de matières
# - SuiviProduction : le suivi général d'une session de production (§5.8)
# - SuiviEau : le suivi spécifique de l'eau, volumes et écarts par étape (§5.9)
# - EtapeProduction : le suivi par étape du processus de fabrication
# - PerteProduction : pertes et rebuts (§5.11)

# Règle importante : le Responsable Production "ne saisit jamais la
# valeur financière des matières" -> aucun champ de prix/coût dans ce
# module (les coûts sont calculés à part, voir apps/couts).

# Règle de verrouillage (§5.14.4) : "Une fois clôturé, l'OF ne doit plus
# être modifiable librement." Voir OrdreFabrication.est_verrouille,
# utilisé par les modèles dépendants (SortieMatiere, RetourMatiere...)
# pour refuser toute nouvelle écriture une fois l'OF CLOTURE ou ANNULE.
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
#     """
#     Le document précise que la prévision "ne doit pas obligatoirement
#     créer immédiatement une sortie de stock. Elle sert surtout à
#     préparer l'activité" (§5.3) - PREVISION est donc le statut de
#     départ, distinct d'un OF réel.
#     """
#     PREVISION = "PREVISION", "Prévision"
#     A_CONVERTIR_EN_OF = "A_CONVERTIR_EN_OF", "À convertir en OF"
#     CONVERTIE = "CONVERTIE", "Convertie en OF"
#     ANNULEE = "ANNULEE", "Annulée"


# class PlanProduction(models.Model):
#     """Le programme / prévision de production (§5.3), avant conversion en OF."""
#     article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
#     date_prevue = models.DateField("Date prévue")
#     quantite_prevue = models.DecimalField("Quantité prévue", max_digits=12, decimal_places=3)
#     priorite = models.CharField("Priorité", max_length=10, choices=Priorite.choices, default=Priorite.NORMALE)
#     commentaire = models.TextField("Commentaire", blank=True)
#     statut = models.CharField(
#         "Statut", max_length=20, choices=StatutPlanProduction.choices,
#         default=StatutPlanProduction.PREVISION,
#     )
#     cree_par = models.ForeignKey(Utilisateur, verbose_name="Créé par", on_delete=models.PROTECT)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Plan de production"
#         verbose_name_plural = "Plans de production"
#         ordering = ["date_prevue"]

#     def __str__(self):
#         return f"Plan {self.article.code} - {self.date_prevue} ({self.quantite_prevue})"

#     def convertir_en_of(self, responsable):
#         """
#         Transforme la prévision en Ordre de Fabrication réel (§5.3 :
#         "Le responsable pourra ensuite convertir la prévision en OF").
#         Crée l'OF (ce qui déclenche automatiquement le calcul des
#         besoins matières, voir OrdreFabrication.save()) et marque la
#         prévision comme convertie.
#         """
#         if self.statut == StatutPlanProduction.CONVERTIE:
#             raise ValueError("Cette prévision a déjà été convertie en OF.")
#         of = OrdreFabrication.objects.create(
#             plan_production=self, article=self.article,
#             quantite_a_produire=self.quantite_prevue, responsable=responsable,
#         )
#         self.statut = StatutPlanProduction.CONVERTIE
#         self.save()
#         return of


# class StatutOF(models.TextChoices):
#     """
#     Workflow exact décrit au §5.4.2 du cahier des charges mis à jour.
#     ANNULE est une branche possible depuis n'importe quel statut avant
#     CLOTURE (voir OrdreFabrication.annuler()), pas une étape de la
#     séquence normale ORDRE_STATUTS_OF.
#     """
#     BROUILLON = "BROUILLON", "Brouillon"
#     A_PREPARER = "A_PREPARER", "À préparer"
#     MATIERES_EN_PREPARATION = "MATIERES_EN_PREPARATION", "Matières en préparation"
#     PRET = "PRET", "Prêt"
#     EN_PRODUCTION = "EN_PRODUCTION", "En production"
#     PRODUCTION_TERMINEE = "PRODUCTION_TERMINEE", "Production terminée"
#     EN_CONTROLE = "EN_CONTROLE", "En contrôle"
#     CLOTURE = "CLOTURE", "Clôturé"
#     ANNULE = "ANNULE", "Annulé"


# # Ordre officiel du workflow normal (hors ANNULE, qui est une branche à part)
# ORDRE_STATUTS_OF = [
#     StatutOF.BROUILLON, StatutOF.A_PREPARER, StatutOF.MATIERES_EN_PREPARATION,
#     StatutOF.PRET, StatutOF.EN_PRODUCTION, StatutOF.PRODUCTION_TERMINEE,
#     StatutOF.EN_CONTROLE, StatutOF.CLOTURE,
# ]


# class OrdreFabrication(models.Model):
#     """
#     L'Ordre de Fabrication (OF) : le document central de la production.
#     Son numéro est unique et automatique (§5.4.1). Son statut ne peut
#     avancer que dans le sens du workflow officiel (ORDRE_STATUTS_OF),
#     sauf annulation qui est une branche à part.
#     """
#     numero = models.CharField("Numéro OF", max_length=30, unique=True, editable=False)
#     plan_production = models.ForeignKey(
#         PlanProduction, verbose_name="Plan de production", on_delete=models.SET_NULL,
#         null=True, blank=True, related_name="ordres_fabrication",
#     )
#     article = models.ForeignKey(Article, verbose_name="Article à produire", on_delete=models.PROTECT)
#     quantite_a_produire = models.DecimalField("Quantité à produire", max_digits=12, decimal_places=3)
#     equipe = models.CharField("Équipe", max_length=100, blank=True)
#     statut = models.CharField(
#         "Statut", max_length=30, choices=StatutOF.choices, default=StatutOF.BROUILLON
#     )
#     motif_annulation = models.TextField(
#         "Motif d'annulation", blank=True,
#         help_text="Renseigné uniquement si l'OF est annulé (§5.4.2).",
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
#     date_debut_production = models.DateTimeField(
#         "Date de début de production", null=True, blank=True,
#         help_text="Renseignée automatiquement au passage à 'En production'.",
#     )
#     date_fin = models.DateTimeField("Date de clôture", null=True, blank=True)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Ordre de fabrication"
#         verbose_name_plural = "Ordres de fabrication"
#         ordering = ["-date_creation"]

#     def __str__(self):
#         return f"{self.numero} - {self.article.code} ({self.get_statut_display()})"

#     def save(self, *args, **kwargs):
#         """
#         Génère le numéro automatique, puis calcule les besoins
#         matières AUTOMATIQUEMENT si c'est une CRÉATION (§5.5 : le
#         calcul se fait dès la création de l'OF, pas à une transition
#         de statut ultérieure).
#         """
#         creation = self._state.adding
#         if not self.numero:
#             self.numero = generer_numero("OF")
#         super().save(*args, **kwargs)
#         if creation:
#             self._calculer_besoins_matieres()

#     @property
#     def est_verrouille(self):
#         """
#         §5.14.4 : "Une fois clôturé, l'OF ne doit plus être modifiable
#         librement." Un OF annulé est également figé. Utilisé par les
#         modèles dépendants pour refuser toute nouvelle écriture.
#         """
#         return self.statut in (StatutOF.CLOTURE, StatutOF.ANNULE)

#     def passer_statut_suivant(self):
#         """Fait avancer l'OF d'une étape dans le workflow officiel."""
#         if self.est_verrouille:
#             raise ValueError(f"L'OF est {self.get_statut_display().lower()}, son statut ne peut plus changer.")

#         index_actuel = ORDRE_STATUTS_OF.index(self.statut)
#         if index_actuel == len(ORDRE_STATUTS_OF) - 1:
#             raise ValueError("L'OF est déjà clôturé, il n'y a pas d'étape suivante.")

#         nouveau_statut = ORDRE_STATUTS_OF[index_actuel + 1]
#         from django.utils import timezone

#         if nouveau_statut == StatutOF.EN_PRODUCTION:
#             self.date_debut_production = timezone.now()
#         if nouveau_statut == StatutOF.CLOTURE:
#             self.date_fin = timezone.now()

#         self.statut = nouveau_statut
#         self.save()
#         return self.statut

#     def annuler(self, motif):
#         """
#         Annule l'OF avec un motif obligatoire. Impossible si déjà
#         clôturé (§5.4.2 : Clôturé est un état final, Annulé en est un autre).
#         """
#         if self.statut == StatutOF.CLOTURE:
#             raise ValueError("Un OF déjà clôturé ne peut plus être annulé.")
#         if not motif:
#             raise ValueError("Le motif d'annulation est obligatoire.")
#         self.statut = StatutOF.ANNULE
#         self.motif_annulation = motif
#         self.save()

#     def _calculer_besoins_matieres(self):
#         """
#         Calcule le besoin théorique de chaque matière en multipliant
#         la quantité à produire par la composition de la fiche
#         technique validée la plus récente de l'article (§5.5).

#         Si aucune fiche technique validée n'existe, ne bloque PAS la
#         création de l'OF (un OF peut exister brièvement le temps de
#         régulariser la fiche technique) mais ne crée aucun besoin :
#         le tableau de bord (voir vues) le signalera comme anomalie.
#         """
#         fiche = (
#             self.article.fiches_techniques
#             .filter(statut="VALIDEE")
#             .order_by("-version")
#             .first()
#         )
#         if fiche is None:
#             return
#         for ligne in fiche.composition.all():
#             BesoinMatierePrevu.objects.update_or_create(
#                 ordre_fabrication=self,
#                 matiere=ligne.matiere,
#                 defaults={
#                     "quantite_theorique": ligne.quantite_necessaire * self.quantite_a_produire
#                 },
#             )

#     def calculer_consommation_reelle(self):
#         """
#         §5.10 : Consommation réelle = Sorties initiales + Sorties
#         complémentaires - Retours magasin. Compare au besoin théorique
#         et calcule l'écart, matière par matière.

#         Retourne une liste de dicts, un par matière ayant eu au moins
#         un mouvement ou un besoin théorique.
#         """
#         from django.db.models import Sum

#         matieres_ids = set(
#             self.besoins_matieres.values_list("matiere_id", flat=True)
#         ) | set(
#             self.sorties_matieres.values_list("matiere_id", flat=True)
#         )

#         resultat = []
#         for matiere_id in matieres_ids:
#             matiere = Article.objects.get(pk=matiere_id)
#             theorique = (
#                 self.besoins_matieres.filter(matiere_id=matiere_id)
#                 .aggregate(total=Sum("quantite_theorique"))["total"] or 0
#             )
#             sorties = (
#                 self.sorties_matieres.filter(matiere_id=matiere_id)
#                 .aggregate(total=Sum("quantite_sortie"))["total"] or 0
#             )
#             retours = (
#                 self.retours_matieres.filter(matiere_id=matiere_id)
#                 .aggregate(total=Sum("quantite_retournee"))["total"] or 0
#             )
#             reelle = sorties - retours
#             ecart = reelle - theorique
#             ecart_pourcentage = (ecart / theorique * 100) if theorique else None

#             resultat.append({
#                 "matiere": matiere.code,
#                 "matiere_designation": matiere.designation,
#                 "theorique": theorique,
#                 "reelle": reelle,
#                 "ecart": ecart,
#                 "ecart_pourcentage": ecart_pourcentage,
#             })
#         return resultat


# class BesoinMatierePrevu(models.Model):
#     """
#     Le besoin théorique en matière pour un OF, calculé automatiquement
#     à la création de l'OF (voir OrdreFabrication._calculer_besoins_matieres).
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

#     def stock_disponible(self):
#         """Somme du stock disponible de cette matière tous dépôts confondus (§5.5, colonne 'Stock disponible')."""
#         from apps.stocks.models import StockArticle
#         from django.db.models import Sum, F
#         agg = StockArticle.objects.filter(article=self.matiere).aggregate(
#             total=Sum(F("quantite_physique") - F("quantite_bloquee") - F("quantite_reservee"))
#         )
#         return agg["total"] or 0

#     def manquant(self):
#         """§5.5, colonne 'Manquant' : partie du besoin non couverte par le stock disponible."""
#         manque = self.quantite_theorique - self.stock_disponible()
#         return manque if manque > 0 else 0

#     def situation(self):
#         """§5.5, colonne 'Situation' : Disponible / Insuffisant."""
#         return "Insuffisant" if self.manquant() > 0 else "Disponible"


# class StatutDemandeMatiere(models.TextChoices):
#     A_PREPARER = "A_PREPARER", "À préparer"
#     PARTIELLEMENT_PREPAREE = "PARTIELLEMENT_PREPAREE", "Partiellement préparée"
#     PREPAREE = "PREPAREE", "Préparée"
#     LIVREE_A_LA_PRODUCTION = "LIVREE_A_LA_PRODUCTION", "Livrée à la production"
#     ANNULEE = "ANNULEE", "Annulée"


# class DemandeMatiere(models.Model):
#     """
#     §5.6 : la demande du Responsable Production au magasin pour les
#     matières nécessaires à un OF. Distincte du besoin théorique
#     (calculé automatiquement) : c'est ici l'acte de DEMANDER
#     concrètement au magasinier de préparer et sortir la matière.
#     """
#     numero = models.CharField("N° demande", max_length=30, unique=True, editable=False)
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="demandes_matieres",
#     )
#     matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
#     quantite_demandee = models.DecimalField("Quantité demandée", max_digits=14, decimal_places=3)
#     demandeur = models.ForeignKey(Utilisateur, verbose_name="Demandeur", on_delete=models.PROTECT)
#     statut = models.CharField(
#         "Statut", max_length=25, choices=StatutDemandeMatiere.choices,
#         default=StatutDemandeMatiere.A_PREPARER,
#     )
#     date_creation = models.DateTimeField("Date", auto_now_add=True)

#     class Meta:
#         verbose_name = "Demande de matière"
#         verbose_name_plural = "Demandes de matières"
#         ordering = ["-date_creation"]

#     def __str__(self):
#         return f"{self.numero} - {self.matiere.code} ({self.get_statut_display()})"

#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("DM")
#         super().save(*args, **kwargs)

#     def livrer_a_production(self, quantite_livree=None):
#         """
#         Le Magasinier livre la matière : génère automatiquement la
#         SortieMatiere correspondante (pas de ressaisie, §15 du cahier
#         des charges) et met à jour le statut de la demande.
#         """
#         if self.ordre_fabrication.est_verrouille:
#             raise ValueError("Cet OF est clôturé ou annulé, impossible de livrer une matière.")
#         quantite_livree = quantite_livree if quantite_livree is not None else self.quantite_demandee
#         SortieMatiere.objects.create(
#             ordre_fabrication=self.ordre_fabrication, matiere=self.matiere,
#             quantite_sortie=quantite_livree, type_sortie=TypeSortie.NORMALE,
#         )
#         self.statut = (
#             StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION
#             if quantite_livree >= self.quantite_demandee
#             else StatutDemandeMatiere.PARTIELLEMENT_PREPAREE
#         )
#         self.save()


# class StatutDemandeComplementaire(models.TextChoices):
#     EN_ATTENTE = "EN_ATTENTE", "En attente"
#     APPROUVEE_ET_LIVREE = "APPROUVEE_ET_LIVREE", "Approuvée et livrée"
#     REJETEE = "REJETEE", "Rejetée"


# class DemandeComplementaire(models.Model):
#     """
#     §5.7 : pendant la production, une demande de matière supplémentaire,
#     avec motif obligatoire ("bouton Demander un complément"). Distincte
#     de DemandeMatiere (la demande initiale). Son approbation génère
#     automatiquement la SortieMatiere COMPLEMENTAIRE correspondante.
#     """
#     numero = models.CharField("N° complément", max_length=30, unique=True, editable=False)
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="demandes_complementaires",
#     )
#     matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
#     quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=3)
#     motif = models.TextField("Motif", help_text="Obligatoire (ex : 'Défauts au soufflage').")
#     demandeur = models.ForeignKey(Utilisateur, verbose_name="Demandeur", on_delete=models.PROTECT)
#     statut = models.CharField(
#         "Statut", max_length=25, choices=StatutDemandeComplementaire.choices,
#         default=StatutDemandeComplementaire.EN_ATTENTE,
#     )
#     date_creation = models.DateTimeField("Date", auto_now_add=True)

#     class Meta:
#         verbose_name = "Demande complémentaire"
#         verbose_name_plural = "Demandes complémentaires"
#         ordering = ["-date_creation"]

#     def __str__(self):
#         return f"{self.numero} - {self.matiere.code} ({self.get_statut_display()})"

#     def save(self, *args, **kwargs):
#         if not self.numero:
#             self.numero = generer_numero("DC")
#         super().save(*args, **kwargs)

#     def approuver_et_livrer(self, utilisateur):
#         """Le Magasinier (ou Responsable Production) approuve : génère la SortieMatiere COMPLEMENTAIRE automatiquement."""
#         if self.ordre_fabrication.est_verrouille:
#             raise ValueError("Cet OF est clôturé ou annulé, impossible de livrer un complément.")
#         SortieMatiere.objects.create(
#             ordre_fabrication=self.ordre_fabrication, matiere=self.matiere,
#             quantite_sortie=self.quantite, type_sortie=TypeSortie.COMPLEMENTAIRE,
#             motif=self.motif, valide_par=utilisateur,
#         )
#         self.statut = StatutDemandeComplementaire.APPROUVEE_ET_LIVREE
#         self.save()

#     def rejeter(self):
#         self.statut = StatutDemandeComplementaire.REJETEE
#         self.save()


# class TypeSortie(models.TextChoices):
#     NORMALE = "NORMALE", "Normale"
#     COMPLEMENTAIRE = "COMPLEMENTAIRE", "Complémentaire (dépassement)"


# class SortieMatiere(models.Model):
#     """
#     Une sortie physique de matière pour un OF. Une sortie
#     COMPLEMENTAIRE exige un motif obligatoire ET une validation
#     (normalement via DemandeComplementaire.approuver_et_livrer, qui
#     remplit motif/valide_par automatiquement).
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
#         help_text="Rempli uniquement pour les sorties complémentaires.",
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
#         if self.ordre_fabrication_id and self.ordre_fabrication.est_verrouille:
#             raise ValidationError(
#                 "Cet OF est clôturé ou annulé : plus aucune sortie matière n'est possible."
#             )


# class RetourMatiere(models.Model):
#     """Matière non utilisée, retournée en stock. Consommation nette = Sorties - Retours (§5.10)."""
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="retours_matieres",
#     )
#     matiere = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
#     quantite_retournee = models.DecimalField("Quantité retournée", max_digits=14, decimal_places=4)
#     motif = models.CharField("Motif", max_length=200, blank=True)
#     date_retour = models.DateTimeField("Date de retour", auto_now_add=True)

#     class Meta:
#         verbose_name = "Retour matière"
#         verbose_name_plural = "Retours matières"

#     def __str__(self):
#         return f"Retour {self.quantite_retournee} {self.matiere.code} de {self.ordre_fabrication.numero}"


# class SuiviProduction(models.Model):
#     """
#     §5.8 : ce qui se passe réellement sur la ligne, saisi par
#     session/journée. Distinct du suivi par étape (EtapeProduction,
#     plus fin, captage/traitement/etc.) : ceci est la synthèse d'une
#     plage horaire de production.
#     """
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.CASCADE, related_name="suivis_production",
#     )
#     date = models.DateField("Date")
#     heure_debut = models.TimeField("Heure de début")
#     heure_fin = models.TimeField("Heure de fin", null=True, blank=True)
#     equipe = models.CharField("Équipe", max_length=100, blank=True)
#     quantite_entree = models.DecimalField("Quantité entrée", max_digits=12, decimal_places=3)
#     quantite_produite = models.DecimalField("Quantité produite", max_digits=12, decimal_places=3, null=True, blank=True)
#     quantite_conforme = models.DecimalField("Quantité conforme", max_digits=12, decimal_places=3, null=True, blank=True)
#     quantite_rejetee = models.DecimalField("Quantité rejetée", max_digits=12, decimal_places=3, null=True, blank=True)
#     arrets = models.TextField("Arrêts", blank=True, help_text="Ex : 'Arrêt 15 min réglage'")
#     incidents = models.TextField("Incidents", blank=True)
#     observations = models.TextField("Observations", blank=True)

#     class Meta:
#         verbose_name = "Suivi de production"
#         verbose_name_plural = "Suivis de production"
#         ordering = ["-date", "-heure_debut"]

#     def __str__(self):
#         return f"{self.ordre_fabrication.numero} - {self.date} {self.heure_debut}"


# class SuiviEau(models.Model):
#     """
#     §5.9 : suivi spécifique de la production d'eau, avec calcul
#     automatique des écarts entre chaque étape du flux (captage ->
#     traitement -> embouteillage). Un seul enregistrement par OF.
#     """
#     ordre_fabrication = models.OneToOneField(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.CASCADE, related_name="suivi_eau",
#     )
#     volume_capte_l = models.DecimalField("Volume capté (L)", max_digits=12, decimal_places=2)
#     volume_envoye_traitement_l = models.DecimalField("Volume envoyé au traitement (L)", max_digits=12, decimal_places=2, null=True, blank=True)
#     volume_obtenu_traitement_l = models.DecimalField("Volume obtenu après traitement (L)", max_digits=12, decimal_places=2)
#     volume_envoye_embouteillage_l = models.DecimalField("Volume envoyé à l'embouteillage (L)", max_digits=12, decimal_places=2)
#     bouteilles_produites = models.PositiveIntegerField("Bouteilles produites")
#     bouteilles_conformes = models.PositiveIntegerField("Bouteilles conformes")
#     bouteilles_rejetees = models.PositiveIntegerField("Bouteilles rejetées", default=0)
#     nombre_packs = models.PositiveIntegerField("Nombre de packs", null=True, blank=True)

#     class Meta:
#         verbose_name = "Suivi de l'eau"
#         verbose_name_plural = "Suivis de l'eau"

#     def __str__(self):
#         return f"Suivi eau - {self.ordre_fabrication.numero}"

#     def _taux(self, perte, entree):
#         return round(float(perte) / float(entree) * 100, 2) if entree else None

#     @property
#     def perte_captage_traitement(self):
#         return self.volume_capte_l - self.volume_obtenu_traitement_l

#     @property
#     def taux_perte_captage_traitement(self):
#         return self._taux(self.perte_captage_traitement, self.volume_capte_l)

#     @property
#     def perte_traitement_embouteillage(self):
#         return self.volume_obtenu_traitement_l - self.volume_envoye_embouteillage_l

#     @property
#     def taux_perte_traitement_embouteillage(self):
#         return self._taux(self.perte_traitement_embouteillage, self.volume_obtenu_traitement_l)

#     @property
#     def taux_perte_embouteillage(self):
#         return self._taux(self.bouteilles_rejetees, self.bouteilles_produites)


# class Etape(models.TextChoices):
#     CAPTAGE = "CAPTAGE", "Captage"
#     TRAITEMENT = "TRAITEMENT", "Traitement"
#     SOUFFLAGE = "SOUFFLAGE", "Soufflage"
#     EMBOUTEILLAGE = "EMBOUTEILLAGE", "Embouteillage"
#     ETIQUETAGE = "ETIQUETAGE", "Étiquetage"
#     CONDITIONNEMENT = "CONDITIONNEMENT", "Conditionnement"


# class EtapeProduction(models.Model):
#     """Suivi de la production étape par étape (processus de fabrication de la fiche technique)."""
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
#     """Causes paramétrables exactes du §5.11 du cahier des charges."""
#     CASSE = "CASSE", "Casse"
#     MAUVAIS_REGLAGE = "MAUVAIS_REGLAGE", "Mauvais réglage"
#     FUITE = "FUITE", "Fuite"
#     DEFAUT_MATIERE = "DEFAUT_MATIERE", "Défaut matière"
#     DEFAUT_BOUTEILLE = "DEFAUT_BOUTEILLE", "Défaut bouteille"
#     CONTROLE_QUALITE = "CONTROLE_QUALITE", "Contrôle qualité"
#     ARRET_MACHINE = "ARRET_MACHINE", "Arrêt machine"
#     NETTOYAGE = "NETTOYAGE", "Nettoyage"
#     ERREUR_OPERATEUR = "ERREUR_OPERATEUR", "Erreur opérateur"
#     AUTRE = "AUTRE", "Autre"


# class PerteProduction(models.Model):
#     """Pertes et rebuts constatés en cours de production (§5.11)."""
#     ordre_fabrication = models.ForeignKey(
#         OrdreFabrication, verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="pertes",
#     )
#     etape = models.ForeignKey(
#         EtapeProduction, verbose_name="Étape concernée", on_delete=models.SET_NULL,
#         null=True, blank=True,
#     )
#     quantite_perte = models.DecimalField("Quantité perdue", max_digits=12, decimal_places=3)
#     taux_perte = models.DecimalField(
#         "Taux de perte (%)", max_digits=5, decimal_places=2, null=True, blank=True,
#         help_text="Peut être calculé côté client (quantité perdue / quantité entrée) ou saisi directement.",
#     )
#     motif = models.CharField("Motif", max_length=30, choices=MotifPerte.choices)
#     observations = models.TextField("Observations", blank=True)
#     date_constat = models.DateTimeField("Date du constat", auto_now_add=True)

#     class Meta:
#         verbose_name = "Perte de production"
#         verbose_name_plural = "Pertes de production"

#     def __str__(self):
#         return f"Perte {self.quantite_perte} sur {self.ordre_fabrication.numero} ({self.get_motif_display()})"



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

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_positif_optionnel,
    exiger_ordre_dates, exiger_pourcentage, valeur_en_base, verifier_transition,
    convertir_decimal,
)


class SaisieSurOFMixin:
    """
    Règles communes à toute saisie rattachée à un OF (sorties, retours,
    suivis, étapes, pertes...) : §5.14.4 "une fois clôturé, l'OF ne doit
    plus être modifiable librement" -> aucune création, modification ni
    suppression sur un OF clôturé ou annulé, et une saisie ne peut pas
    être déplacée vers un autre OF.
    """

    def controler_of(self):
        if self.pk and valeur_en_base(self, "ordre_fabrication") != self.ordre_fabrication_id:
            raise ValidationError({"ordre_fabrication": "L'OF d'une saisie existante ne peut pas être changé."})
        if self.ordre_fabrication_id and self.ordre_fabrication.est_verrouille:
            of = self.ordre_fabrication
            raise ValidationError({"ordre_fabrication": (
                f"L'OF {of.numero} est {of.get_statut_display().lower()} : plus aucune saisie n'est possible."
            )})

    def controler_of_en_production(self):
        """
        Saisies du RÉEL (suivi, étapes, suivi eau, pertes) : l'OF doit
        avoir démarré. Rien avant « En production » (on ne constate pas
        une production qui n'a pas commencé) ; corrections possibles
        jusqu'au contrôle, puis figé à la clôture.
        """
        self.controler_of()
        if self.ordre_fabrication_id:
            of = self.ordre_fabrication
            if of.statut not in STATUTS_SAISIE_REELLE:
                raise ValidationError({"ordre_fabrication": (
                    f"L'OF {of.numero} est « {of.get_statut_display()} » : la production n'a pas "
                    "encore démarré, aucune saisie du réel n'est possible."
                )})

    def verifier_suppression(self):
        of = self.ordre_fabrication
        if of.est_verrouille:
            raise ValidationError(f"L'OF {of.numero} est {of.get_statut_display().lower()} : ses saisies sont figées.")


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


class PlanProduction(ValidationAvantEnregistrement, models.Model):
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

    TRANSITIONS = {
        StatutPlanProduction.PREVISION: {
            StatutPlanProduction.A_CONVERTIR_EN_OF, StatutPlanProduction.CONVERTIE, StatutPlanProduction.ANNULEE,
        },
        StatutPlanProduction.A_CONVERTIR_EN_OF: {
            StatutPlanProduction.PREVISION, StatutPlanProduction.CONVERTIE, StatutPlanProduction.ANNULEE,
        },
    }

    def clean(self):
        exiger_positif(self.quantite_prevue, "quantite_prevue", "La quantité prévue")
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutPlanProduction.CONVERTIE, StatutPlanProduction.ANNULEE):
            raise ValidationError(
                f"Cette prévision est {dict(StatutPlanProduction.choices)[ancien_statut].lower()} : "
                "elle ne peut plus être modifiée."
            )
        verifier_transition(ancien_statut, self.statut, self.TRANSITIONS, "statut de la prévision")
        if ancien_statut is None and self.statut == StatutPlanProduction.CONVERTIE:
            raise ValidationError({"statut": "Une prévision passe à « Convertie » uniquement via l'action de conversion en OF."})

    @transaction.atomic
    def convertir_en_of(self, responsable, agents=None):
        """
        Transforme la prévision en Ordre de Fabrication réel (§5.3 :
        "Le responsable pourra ensuite convertir la prévision en OF").
        Crée l'OF (ce qui déclenche automatiquement le calcul des
        besoins matières, voir OrdreFabrication.save()) et marque la
        prévision comme convertie.
        """
        if self.statut == StatutPlanProduction.CONVERTIE:
            raise ValueError("Cette prévision a déjà été convertie en OF.")
        if self.statut == StatutPlanProduction.ANNULEE:
            raise ValueError("Cette prévision est annulée : elle ne peut pas être convertie en OF.")
        of = OrdreFabrication.objects.create(
            plan_production=self, article=self.article,
            quantite_a_produire=self.quantite_prevue, responsable=responsable,
        )
        if agents:
            of.affecter_agents(agents, par=responsable)
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
# Statuts où l'on peut saisir le réel de production (voir SaisieSurOFMixin).
STATUTS_SAISIE_REELLE = ("EN_PRODUCTION", "PRODUCTION_TERMINEE", "EN_CONTROLE")

ORDRE_STATUTS_OF = [
    StatutOF.BROUILLON, StatutOF.A_PREPARER, StatutOF.MATIERES_EN_PREPARATION,
    StatutOF.PRET, StatutOF.EN_PRODUCTION, StatutOF.PRODUCTION_TERMINEE,
    StatutOF.EN_CONTROLE, StatutOF.CLOTURE,
]


class OrdreFabrication(ValidationAvantEnregistrement, models.Model):
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
    ligne = models.ForeignKey(
        "industriel.Ligne", verbose_name="Ligne", on_delete=models.PROTECT, null=True, blank=True,
        related_name="ordres_fabrication",
        help_text="Ligne compatible avec le format. Détermine l'usine (magasin matières et stock produits finis).",
    )
    circuit = models.ForeignKey(
        "industriel.Circuit", verbose_name="Circuit", on_delete=models.PROTECT, null=True, blank=True,
        related_name="ordres_fabrication", help_text="Associé automatiquement (circuit validé le plus précis).",
    )
    fiche_technique = models.ForeignKey(
        "referentiel.FicheTechnique", verbose_name="Recette appliquée", on_delete=models.PROTECT,
        null=True, blank=True, related_name="ordres_fabrication", editable=False,
    )
    date_prevue = models.DateField("Date prévue", null=True, blank=True)
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
        recalcul = creation or (
            valeur_en_base(self, "quantite_a_produire") != self.quantite_a_produire
            or valeur_en_base(self, "article") != self.article_id
        )
        if self.statut == StatutOF.BROUILLON and self.article_id and (
            (creation and self.circuit_id is None)
            or (not creation and (recalcul or valeur_en_base(self, "ligne") != self.ligne_id))
        ):
            # Association automatique du circuit validé le plus précis.
            from apps.industriel.models import circuit_pour
            self.circuit = circuit_pour(self.article, self.ligne)
        with transaction.atomic():
            if not self.numero:
                self.numero = generer_numero("OF")
            super().save(*args, **kwargs)
            if recalcul:
                # Création, ou quantité/article corrigés tant que l'OF est
                # en brouillon (voir clean) : les besoins doivent suivre.
                self.besoins_matieres.all().delete()
                self._calculer_besoins_matieres()

    def clean(self):
        """
        - quantité à produire strictement positive, article fabriqué et actif ;
        - un OF clôturé ou annulé est figé (§5.14.4) ;
        - le statut ne progresse que d'une étape à la fois dans le
          workflow officiel, ou passe à Annulé (voir passer_statut_suivant
          et annuler) ; un OF est toujours créé en brouillon ;
        - article et quantité ne changent plus après le brouillon (les
          besoins matières et les sorties en dépendent).
        """
        exiger_positif(self.quantite_a_produire, "quantite_a_produire", "La quantité à produire")
        if self.article_id:
            if not self.article.actif:
                raise ValidationError({"article": f"L'article {self.article.code} est inactif."})
            from apps.referentiel.models import TYPES_NON_FABRIQUES
            if self.article.type_article in TYPES_NON_FABRIQUES:
                raise ValidationError({"article": (
                    f"On ne fabrique pas un article « {self.article.get_type_article_display()} » : "
                    "choisissez un produit fini, intermédiaire ou un fluide de process."
                )})
            if self._state.adding:
                fiche = self.article.fiche_technique_validee
                if fiche is None or not fiche.composition.exists():
                    raise ValidationError({"article": (
                        f"Aucune fiche de composition validée pour {self.article.code} : "
                        "l'ADMIN_SI doit paramétrer et valider sa composition avant de lancer un OF."
                    )})
        self.controler_ligne_et_circuit()

        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutOF.CLOTURE, StatutOF.ANNULE):
            raise ValidationError(
                f"L'OF {self.numero} est {dict(StatutOF.choices)[ancien_statut].lower()} : il ne peut plus être modifié."
            )
        if ancien_statut is None:
            if self.statut != StatutOF.BROUILLON:
                raise ValidationError({"statut": "Un OF est toujours créé en brouillon."})
            return
        if self.statut != ancien_statut and self.statut != StatutOF.ANNULE:
            index_ancien = ORDRE_STATUTS_OF.index(ancien_statut)
            if index_ancien + 1 >= len(ORDRE_STATUTS_OF) or ORDRE_STATUTS_OF[index_ancien + 1] != self.statut:
                raise ValidationError({"statut": (
                    f"Passage de l'OF de « {ancien_statut} » à « {self.statut} » non autorisé : "
                    "le statut avance d'une étape à la fois (action /avancer_statut/)."
                )})
        if ancien_statut != StatutOF.BROUILLON:
            if valeur_en_base(self, "article") != self.article_id:
                raise ValidationError({"article": "L'article d'un OF ne peut plus être changé après le brouillon."})
            if valeur_en_base(self, "quantite_a_produire") != self.quantite_a_produire:
                raise ValidationError({"quantite_a_produire": "La quantité d'un OF ne peut plus être changée après le brouillon."})
            for champ in ("ligne", "circuit"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "La ligne et le circuit d'un OF ne changent plus après le brouillon."})

    def controler_ligne_et_circuit(self):
        """
        Guide Jus §8 : « choix de la ligne/circuit compatible ». La ligne
        doit être active, de l'activité du produit et accepter ce format ;
        le circuit doit être validé, de la même activité, et propre à ce
        format / cette ligne s'il en désigne un.
        """
        if not self.article_id:
            return
        if self.ligne_id:
            ligne = self.ligne
            if not ligne.actif:
                raise ValidationError({"ligne": f"La ligne {ligne.code} est inactive."})
            if not ligne.accepte(self.article):
                raise ValidationError({"ligne": f"La ligne {ligne.code} n'est pas compatible avec {self.article.code}."})
        if self.circuit_id:
            circuit = self.circuit
            if circuit.statut != "VALIDE" and valeur_en_base(self, "circuit") != self.circuit_id:
                raise ValidationError({"circuit": f"Le circuit {circuit.code} n'est pas validé."})
            if self.article.activite_id and circuit.activite_id != self.article.activite_id:
                raise ValidationError({"circuit": f"Le circuit {circuit.code} est un circuit {circuit.activite.code}."})
            if circuit.article_id and circuit.article_id != self.article_id:
                raise ValidationError({"circuit": f"Le circuit {circuit.code} est réservé à un autre format."})
            if circuit.ligne_id and circuit.ligne_id != self.ligne_id:
                raise ValidationError({"circuit": f"Le circuit {circuit.code} est propre à la ligne {circuit.ligne.code}."})

    # --- Contexte industriel ---
    @property
    def usine(self):
        return self.ligne.usine if self.ligne_id else None

    @property
    def activite(self):
        return self.article.activite if self.article_id else None

    @property
    def depot_matieres(self):
        from apps.stocks.models import depot_matieres
        return depot_matieres(self.usine)

    @property
    def depot_produits_finis(self):
        from apps.stocks.models import depot_produits_finis
        return depot_produits_finis(self.usine)

    @property
    def quantite_produite_bonne(self):
        """Quantité réellement produite et bonne : lots non « non conformes », à défaut la quantité prévue."""
        from django.db.models import Sum
        total = self.lots.exclude(statut="NON_CONFORME").aggregate(total=Sum("quantite"))["total"]
        return total or self.quantite_a_produire

    def etapes_prevues(self):
        """Étapes du circuit de l'OF, dans l'ordre (vide sans circuit)."""
        if not self.circuit_id:
            return []
        return list(self.circuit.etapes.select_related("etape", "poste", "equipement").order_by("ordre"))

    def volume_eau(self):
        """
        Volume d'eau traitée utilisé par l'OF (clé de répartition du forage
        et du traitement) : {"litres": ..., "statut": "MESURE" | "CALCULE" | None}.
        - mesuré : suivi eau de l'OF (volume envoyé à l'embouteillage) ;
        - calculé : consommation réelle d'articles « fluide de process »
          mesurés en L ou m³ (sorties - retours), sinon besoin théorique ;
        - None si aucune donnée : pas de clé inventée.
        """
        from decimal import Decimal
        from django.db.models import Sum
        suivi = SuiviEau.objects.filter(ordre_fabrication_id=self.pk).first()
        if suivi is not None and suivi.volume_envoye_embouteillage_l:
            return {"litres": Decimal(suivi.volume_envoye_embouteillage_l), "statut": "MESURE"}
        total = Decimal(0)
        trouve = False
        for unite, facteur in (("L", Decimal(1)), ("M3", Decimal(1000))):
            sorties = self.sorties_matieres.filter(
                matiere__type_article="FLUIDE_PROCESS", matiere__unite_mesure=unite,
            ).aggregate(t=Sum("quantite_sortie"))["t"]
            retours = self.retours_matieres.filter(
                matiere__type_article="FLUIDE_PROCESS", matiere__unite_mesure=unite,
            ).aggregate(t=Sum("quantite_retournee"))["t"]
            if sorties:
                trouve = True
                total += (Decimal(sorties) - Decimal(retours or 0)) * facteur
        if not trouve:
            for unite, facteur in (("L", Decimal(1)), ("M3", Decimal(1000))):
                besoin = self.besoins_matieres.filter(
                    matiere__type_article="FLUIDE_PROCESS", matiere__unite_mesure=unite,
                ).aggregate(t=Sum("quantite_theorique"))["t"]
                if besoin:
                    trouve = True
                    total += Decimal(besoin) * facteur
        return {"litres": total, "statut": "CALCULE"} if trouve else {"litres": None, "statut": None}

    def verifier_stock_pour_lancement(self):
        """
        Guide Jus §8 : « blocage du lancement si un besoin obligatoire est
        insuffisant ». Compare chaque besoin au stock disponible du magasin
        matières de l'usine de l'OF. Retourne la liste des manques.
        """
        from apps.stocks.models import StockArticle
        manques = []
        depot = self.depot_matieres
        for besoin in self.besoins_matieres.select_related("matiere"):
            stock = StockArticle.objects.filter(article_id=besoin.matiere_id, depot=depot).first()
            disponible = stock.quantite_disponible if stock else 0
            if disponible < besoin.quantite_theorique:
                manques.append({
                    "matiere": besoin.matiere.code, "designation": besoin.matiere.designation,
                    "besoin": besoin.quantite_theorique, "disponible": disponible,
                    "manquant": besoin.quantite_theorique - disponible,
                })
        return manques

    def verifier_suppression(self):
        if self.statut != StatutOF.BROUILLON or self.sorties_matieres.exists():
            raise ValidationError("Seul un OF en brouillon sans aucune sortie matière peut être supprimé ; sinon, annulez-le.")

    @property
    def est_verrouille(self):
        """
        §5.14.4 : "Une fois clôturé, l'OF ne doit plus être modifiable
        librement." Un OF annulé est également figé. Utilisé par les
        modèles dépendants pour refuser toute nouvelle écriture.
        """
        return self.statut in (StatutOF.CLOTURE, StatutOF.ANNULE)

    @transaction.atomic
    def passer_statut_suivant(self):
        """Fait avancer l'OF d'une étape dans le workflow officiel."""
        if self.est_verrouille:
            raise ValueError(f"L'OF est {self.get_statut_display().lower()}, son statut ne peut plus changer.")

        index_actuel = ORDRE_STATUTS_OF.index(self.statut)
        if index_actuel == len(ORDRE_STATUTS_OF) - 1:
            raise ValueError("L'OF est déjà clôturé, il n'y a pas d'étape suivante.")

        nouveau_statut = ORDRE_STATUTS_OF[index_actuel + 1]
        from django.utils import timezone

        if nouveau_statut == StatutOF.A_PREPARER:
            from apps.production.models import ParametreProduction
            manques = self.verifier_stock_pour_lancement()
            if manques and ParametreProduction.courant().bloquer_lancement_stock_insuffisant:
                raise ValueError(
                    f"Lancement de l'OF {self.numero} bloqué : stock insuffisant au « {self.depot_matieres.nom} » pour "
                    + ", ".join(f"{m['matiere']} (besoin {m['besoin']:.3f}, disponible {m['disponible']:.3f})" for m in manques)
                    + ". Approvisionnez ou ajustez la quantité."
                )
        if nouveau_statut == StatutOF.CLOTURE:
            from apps.qualite.models import blocages_qualite_of
            blocages = blocages_qualite_of(self)
            if blocages:
                raise ValueError(f"Clôture de l'OF {self.numero} impossible : " + " ; ".join(blocages) + ".")

        if nouveau_statut == StatutOF.EN_PRODUCTION:
            self.date_debut_production = timezone.now()
        if nouveau_statut == StatutOF.CLOTURE:
            self.date_fin = timezone.now()

        self.statut = nouveau_statut
        self.save()
        if nouveau_statut == StatutOF.EN_PRODUCTION:
            from apps.qualite.models import generer_controles
            generer_controles(self, declencheurs=("DEMARRAGE", "CHAQUE_OF", "PERIODIQUE"))
        if nouveau_statut == StatutOF.PRODUCTION_TERMINEE:
            from apps.comptabilite.anomalies import controler_consommation_of
            controler_consommation_of(self)
        if nouveau_statut == StatutOF.CLOTURE:
            from apps.couts.models import CoutReel
            cout_reel, _ = CoutReel.objects.get_or_create(ordre_fabrication=self)
            cout_reel.calculer()
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

        Un OF ne peut être créé que si l'article a une fiche validée
        avec composition (voir clean) : les besoins sont donc toujours
        calculés.
        """
        fiche = self.article.fiche_technique_validee
        if fiche is None:
            return
        from decimal import Decimal
        if self.fiche_technique_id != fiche.pk:
            self.fiche_technique = fiche
            OrdreFabrication.objects.filter(pk=self.pk).update(fiche_technique=fiche)
        cumul = {}
        for ligne, quantite in fiche.besoins_pour(self.article, self.quantite_a_produire):
            # Chiffrage : besoin x prix unitaire de la fiche, FIGÉ dans l'OF (un
            # changement de prix ultérieur ne modifie pas les OF déjà lancés).
            precedent = cumul.get(ligne.matiere_id)
            cumul[ligne.matiere_id] = (ligne, quantite + (precedent[1] if precedent else 0))
        for ligne, quantite in cumul.values():
            BesoinMatierePrevu.objects.update_or_create(
                ordre_fabrication=self,
                matiere=ligne.matiere,
                defaults={
                    "quantite_theorique": quantite,
                    "prix_unitaire": ligne.prix_unitaire,
                    "montant": (quantite * ligne.prix_unitaire).quantize(Decimal("0.01")),
                },
            )

    @property
    def montant_total_matieres(self):
        """Montant total des éléments nécessaires à l'OF (somme des besoins chiffrés)."""
        from django.db.models import Sum
        return self.besoins_matieres.aggregate(total=Sum("montant"))["total"] or 0

    @staticmethod
    def verifier_agents(agents):
        """Seuls des comptes Agent Production actifs peuvent être affectés à un OF."""
        invalides = [
            agent.username for agent in agents
            if agent.profil != "AGENT_PRODUCTION" or not agent.is_active
        ]
        if invalides:
            raise ValidationError({"agents_affectes": (
                "Seuls des comptes Agent Production actifs peuvent être affectés : " + ", ".join(invalides) + "."
            )})

    @transaction.atomic
    def affecter_agents(self, agents, par):
        """
        Le Responsable Production définit les agents autorisés sur l'OF
        (remplace la liste). Tracé dans le journal des actions : qui,
        quand, agents ajoutés / retirés (journal automatique).
        """
        if self.est_verrouille:
            raise ValidationError(f"L'OF {self.numero} est {self.get_statut_display().lower()} : l'affectation est figée.")
        agents = list(agents)
        self.verifier_agents(agents)
        avant = set(self.agents_affectes.values_list("username", flat=True))
        nouveaux = [agent for agent in agents if agent.username not in avant]
        self.agents_affectes.set(agents)   # ajouts / retraits tracés par le journal automatique
        if nouveaux:
            from apps.core.notifications import notifier
            notifier(
                "Vous êtes affecté à un OF", f"{self.numero} - {self.article.designation} x {self.quantite_a_produire}",
                document=self, utilisateurs=nouveaux,
            )

    @transaction.atomic
    def demander_matieres(self, demandeur):
        """
        Le Responsable Production demande au magasin TOUTE la composition
        de l'OF en une seule fois : une DemandeMatiere par matière de la
        fiche, pour la quantité théorique (composition x quantité à
        produire). Un besoin supplémentaire en cours de production passe
        ensuite par une DemandeComplementaire (§5.7).
        """
        from decimal import Decimal, ROUND_UP
        if self.est_verrouille:
            raise ValueError(f"L'OF {self.numero} est {self.get_statut_display().lower()} : aucune demande possible.")
        if self.demandes_matieres.exclude(statut=StatutDemandeMatiere.ANNULEE).exists():
            raise ValueError(
                f"Les matières de l'OF {self.numero} ont déjà été demandées au magasin. "
                "Pour un besoin supplémentaire, faites une demande complémentaire."
            )
        besoins = list(self.besoins_matieres.select_related("matiere"))
        if not besoins:
            raise ValueError(f"L'OF {self.numero} n'a aucun besoin matière (fiche de composition vide ?).")
        return [
            DemandeMatiere.objects.create(
                ordre_fabrication=self, matiere=besoin.matiere, demandeur=demandeur,
                # quantite_theorique a 4 décimales, la demande 3 : on arrondit
                # au-dessus pour ne jamais demander moins que nécessaire.
                quantite_demandee=quantite,
                prix_unitaire=besoin.prix_unitaire,
                montant=(quantite * besoin.prix_unitaire).quantize(Decimal("0.01")),
            )
            for besoin in besoins
            for quantite in [besoin.quantite_theorique.quantize(Decimal("0.001"), rounding=ROUND_UP)]
        ]

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
    prix_unitaire = models.DecimalField(
        "Prix unitaire", max_digits=14, decimal_places=2, default=0,
        help_text="Prix de la fiche technique au moment de la création de l'OF (figé).",
    )
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2, default=0)

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


class DemandeMatiere(ValidationAvantEnregistrement, models.Model):
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
    prix_unitaire = models.DecimalField(
        "Prix unitaire", max_digits=14, decimal_places=2, default=0,
        help_text="Repris du besoin chiffré de l'OF.",
    )
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2, default=0)
    quantite_livree = models.DecimalField(
        "Quantité déjà livrée", max_digits=14, decimal_places=3, default=0,
        help_text="Cumul des livraisons (partielles) du magasin : empêche de livrer plus que demandé.",
    )
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

    TRANSITIONS = {
        StatutDemandeMatiere.A_PREPARER: {
            StatutDemandeMatiere.PREPAREE, StatutDemandeMatiere.PARTIELLEMENT_PREPAREE,
            StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION, StatutDemandeMatiere.ANNULEE,
        },
        StatutDemandeMatiere.PREPAREE: {
            StatutDemandeMatiere.A_PREPARER, StatutDemandeMatiere.PARTIELLEMENT_PREPAREE,
            StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION, StatutDemandeMatiere.ANNULEE,
        },
        StatutDemandeMatiere.PARTIELLEMENT_PREPAREE: {
            StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION, StatutDemandeMatiere.ANNULEE,
        },
    }

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("DM")
        super().save(*args, **kwargs)

    def clean(self):
        exiger_positif(self.quantite_demandee, "quantite_demandee", "La quantité demandée")
        if self.ordre_fabrication_id and self.ordre_fabrication.est_verrouille:
            raise ValidationError({"ordre_fabrication": "Cet OF est clôturé ou annulé : aucune demande de matière possible."})
        if self.ordre_fabrication_id and self.matiere_id and not self.ordre_fabrication.besoins_matieres.filter(
            matiere_id=self.matiere_id,
        ).exists():
            raise ValidationError({"matiere": (
                f"{self.matiere.code} ne fait pas partie de la composition de l'OF "
                f"{self.ordre_fabrication.numero} : utilisez une demande complémentaire."
            )})
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION, StatutDemandeMatiere.ANNULEE):
            raise ValidationError(
                f"Cette demande est {dict(StatutDemandeMatiere.choices)[ancien_statut].lower()} : elle ne peut plus être modifiée."
            )
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de la demande",
            initial=StatutDemandeMatiere.A_PREPARER,
        )
        if self.pk and self.quantite_livree > 0:
            for champ in ("ordre_fabrication", "matiere"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Modification impossible : une partie a déjà été livrée."})
        if self.quantite_demandee is not None and self.quantite_demandee < self.quantite_livree:
            raise ValidationError({"quantite_demandee": (
                f"La quantité demandée ne peut pas être inférieure à la quantité déjà livrée ({self.quantite_livree})."
            )})

    def verifier_suppression(self):
        if self.quantite_livree > 0:
            raise ValidationError("Cette demande a déjà été (partiellement) livrée : annulez-la plutôt.")

    @transaction.atomic
    def livrer_a_production(self, quantite_livree=None):
        """
        Le Magasinier livre la matière : génère automatiquement la
        SortieMatiere correspondante (pas de ressaisie, §15 du cahier
        des charges) et met à jour le statut de la demande.

        Sans quantité fournie, livre le reste à livrer. Refuse de livrer
        une demande déjà livrée/annulée ou plus que le reste à livrer
        (auparavant, chaque appel créait une nouvelle sortie complète).
        Le stock est vérifié par la sortie elle-même (MouvementStock).
        """
        if self.ordre_fabrication.est_verrouille:
            raise ValueError("Cet OF est clôturé ou annulé, impossible de livrer une matière.")
        if self.statut in (StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION, StatutDemandeMatiere.ANNULEE):
            raise ValueError(f"Cette demande est {self.get_statut_display().lower()} : plus rien à livrer.")
        reste = self.quantite_demandee - self.quantite_livree
        quantite = convertir_decimal(quantite_livree, "La quantité livrée", obligatoire=False)
        if quantite is None:
            quantite = reste
        if quantite > reste:
            raise ValueError(f"Quantité livrée ({quantite}) supérieure au reste à livrer ({reste}).")
        SortieMatiere.objects.create(
            ordre_fabrication=self.ordre_fabrication, matiere=self.matiere,
            quantite_sortie=quantite, type_sortie=TypeSortie.NORMALE,
        )
        self.quantite_livree += quantite
        self.statut = (
            StatutDemandeMatiere.LIVREE_A_LA_PRODUCTION
            if self.quantite_livree >= self.quantite_demandee
            else StatutDemandeMatiere.PARTIELLEMENT_PREPAREE
        )
        self.save()


class StatutDemandeComplementaire(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    APPROUVEE_ET_LIVREE = "APPROUVEE_ET_LIVREE", "Approuvée et livrée"
    REJETEE = "REJETEE", "Rejetée"


class DemandeComplementaire(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        exiger_positif(self.quantite, "quantite", "La quantité")
        if not (self.motif or "").strip():
            raise ValidationError({"motif": "Le motif est obligatoire pour une demande complémentaire."})
        if self.ordre_fabrication_id and self.ordre_fabrication.est_verrouille:
            raise ValidationError({"ordre_fabrication": "Cet OF est clôturé ou annulé : aucune demande complémentaire possible."})
        if self.pk is None and self.ordre_fabrication_id and self.ordre_fabrication.statut != StatutOF.EN_PRODUCTION:
            raise ValidationError({"ordre_fabrication": (
                "Une demande complémentaire se fait pendant la production (§5.7) : "
                f"l'OF {self.ordre_fabrication.numero} est « {self.ordre_fabrication.get_statut_display()} »."
            )})
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut not in (None, StatutDemandeComplementaire.EN_ATTENTE):
            raise ValidationError("Cette demande a déjà été traitée : elle ne peut plus être modifiée.")
        verifier_transition(
            ancien_statut, self.statut,
            {StatutDemandeComplementaire.EN_ATTENTE: {
                StatutDemandeComplementaire.APPROUVEE_ET_LIVREE, StatutDemandeComplementaire.REJETEE,
            }},
            "statut de la demande", initial=StatutDemandeComplementaire.EN_ATTENTE,
        )

    def verifier_suppression(self):
        if self.statut != StatutDemandeComplementaire.EN_ATTENTE:
            raise ValidationError("Une demande déjà traitée ne peut pas être supprimée.")

    @transaction.atomic
    def approuver_et_livrer(self, utilisateur):
        """Le Magasinier (ou Responsable Production) approuve : génère la SortieMatiere COMPLEMENTAIRE automatiquement."""
        if self.statut != StatutDemandeComplementaire.EN_ATTENTE:
            raise ValueError(f"Cette demande est déjà {self.get_statut_display().lower()}.")
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
        if self.statut != StatutDemandeComplementaire.EN_ATTENTE:
            raise ValueError(f"Cette demande est déjà {self.get_statut_display().lower()}.")
        self.statut = StatutDemandeComplementaire.REJETEE
        self.save()


class TypeSortie(models.TextChoices):
    NORMALE = "NORMALE", "Normale"
    COMPLEMENTAIRE = "COMPLEMENTAIRE", "Complémentaire (dépassement)"


class SortieMatiere(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
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
    lot_matiere = models.ForeignKey(
        "stocks.LotMatiere", verbose_name="Lot imposé", on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", help_text="Vide = lots consommés automatiquement, les plus anciens (DLC) d'abord.",
    )
    date_sortie = models.DateTimeField("Date de sortie", auto_now_add=True)

    class Meta:
        verbose_name = "Sortie matière"
        verbose_name_plural = "Sorties matières"
        ordering = ["-date_sortie"]

    def __str__(self):
        return f"Sortie {self.quantite_sortie} {self.matiere.code} pour {self.ordre_fabrication.numero}"

    def clean(self):
        """
        Vérifié AVANT tout enregistrement (auparavant la vue enregistrait
        la sortie - donc le mouvement de stock - puis supprimait la sortie
        si clean() échouait, en laissant le mouvement : stock faux).
        Le stock disponible est contrôlé par le MouvementStock créé dans
        la même transaction.
        """
        if self.pk is not None:
            raise ValidationError("Une sortie matière enregistrée ne peut pas être modifiée.")
        exiger_positif(self.quantite_sortie, "quantite_sortie", "La quantité sortie")
        if self.type_sortie == TypeSortie.COMPLEMENTAIRE and not (self.motif or "").strip():
            raise ValidationError({"motif": "Le motif est obligatoire pour une sortie complémentaire."})
        self.controler_of()

    def verifier_suppression(self):
        raise ValidationError("Une sortie matière ne peut pas être supprimée (le stock a déjà été mouvementé) : faites un retour matière.")

    def save(self, *args, **kwargs):
        """
        Une sortie matière DOIT diminuer le stock réel du magasin
        (§8/§15 : pas de ressaisie, traçabilité totale). On génère donc
        systématiquement le MouvementStock SORTIE correspondant, qui
        sera répercuté sur StockArticle par le signal de
        apps/stocks/signals.py. Ne se déclenche qu'à la création : une
        SortieMatiere n'est jamais modifiée après coup dans ce projet.
        """
        creation = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creation:
                self._creer_mouvement_sortie()

    def _stock_suffisant(self, depot):
        from apps.stocks.models import StockArticle
        stock = StockArticle.objects.filter(article_id=self.matiere_id, depot=depot).first()
        return stock is not None and stock.quantite_disponible >= self.quantite_sortie

    def _creer_mouvement_sortie(self):
        from apps.stocks.models import MouvementStock, TypeMouvement, LotMatiere
        depot = self.ordre_fabrication.depot_matieres
        # Le mouvement contrôle d'abord le stock disponible ; les lots consommés
        # (les plus proches de leur DLC d'abord) sont tracés ensuite.
        allocation = LotMatiere.allouer(self.matiere, depot, self.quantite_sortie, lot_impose=self.lot_matiere) \
            if self._stock_suffisant(depot) else []
        for lot, quantite in allocation:
            ConsommationLotMatiere.objects.create(sortie=self, lot=lot, quantite=quantite)
            lot.consommer(quantite)
        MouvementStock.objects.create(
            article=self.matiere,
            depot=depot,
            type_mouvement=TypeMouvement.SORTIE,
            quantite=self.quantite_sortie,
            motif=self.motif or f"Sortie matière OF {self.ordre_fabrication.numero}",
            document_origine=self.ordre_fabrication.numero,
            utilisateur=self.valide_par or self.ordre_fabrication.responsable,
        )


class RetourMatiere(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        """On ne peut retourner que ce qui a été sorti pour cet OF (sorties - retours déjà faits)."""
        from django.db.models import Sum
        if self.pk is not None:
            raise ValidationError("Un retour matière enregistré ne peut pas être modifié.")
        exiger_positif(self.quantite_retournee, "quantite_retournee", "La quantité retournée")
        self.controler_of()
        if self.ordre_fabrication_id and self.matiere_id:
            sorti = SortieMatiere.objects.filter(
                ordre_fabrication_id=self.ordre_fabrication_id, matiere_id=self.matiere_id,
            ).aggregate(total=Sum("quantite_sortie"))["total"] or 0
            deja_retourne = RetourMatiere.objects.filter(
                ordre_fabrication_id=self.ordre_fabrication_id, matiere_id=self.matiere_id,
            ).aggregate(total=Sum("quantite_retournee"))["total"] or 0
            retournable = sorti - deja_retourne
            if self.quantite_retournee > retournable:
                raise ValidationError({"quantite_retournee": (
                    f"Retour impossible : seulement {retournable} de {self.matiere.code} "
                    f"peut être retourné pour l'OF {self.ordre_fabrication.numero} "
                    f"(sorti {sorti}, déjà retourné {deja_retourne})."
                )})

    def verifier_suppression(self):
        raise ValidationError("Un retour matière ne peut pas être supprimé (le stock a déjà été mouvementé).")

    def save(self, *args, **kwargs):
        """
        Symétrique de SortieMatiere.save() : un retour magasin
        recrédite le stock réel (§5.10 : consommation nette = Sorties
        - Retours, ce qui suppose que les retours remontent bien le
        stock physique, pas seulement le calcul théorique).
        """
        creation = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creation:
                self._creer_mouvement_retour()

    def _creer_mouvement_retour(self):
        from apps.stocks.models import MouvementStock, TypeMouvement
        # La matière retourne dans les lots dont elle était sortie (le dernier consommé d'abord).
        reste = self.quantite_retournee
        for consommation in ConsommationLotMatiere.objects.filter(
            sortie__ordre_fabrication_id=self.ordre_fabrication_id, sortie__matiere_id=self.matiere_id,
        ).select_related("lot").order_by("-pk"):
            if reste <= 0:
                break
            retournable = consommation.quantite - consommation.quantite_retournee
            if retournable <= 0:
                continue
            quantite = min(retournable, reste)
            consommation.quantite_retournee += quantite
            consommation.save(update_fields=["quantite_retournee"])
            consommation.lot.restituer(quantite)
            reste -= quantite
        MouvementStock.objects.create(
            article=self.matiere,
            depot=self.ordre_fabrication.depot_matieres,
            type_mouvement=TypeMouvement.RETOUR,
            quantite=self.quantite_retournee,
            motif=self.motif or f"Retour matière OF {self.ordre_fabrication.numero}",
            document_origine=self.ordre_fabrication.numero,
            utilisateur=self.ordre_fabrication.responsable,
        )


class SuiviProduction(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
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
    saisi_par = models.ForeignKey(
        Utilisateur, verbose_name="Saisi par", on_delete=models.PROTECT,
        null=True, blank=True, related_name="suivis_production_saisis",
        help_text="Traçabilité : renseigné automatiquement avec l'utilisateur connecté.",
    )

    class Meta:
        verbose_name = "Suivi de production"
        verbose_name_plural = "Suivis de production"
        ordering = ["-date", "-heure_debut"]

    def __str__(self):
        return f"{self.ordre_fabrication.numero} - {self.date} {self.heure_debut}"

    def clean(self):
        self.controler_of_en_production()
        exiger_positif(self.quantite_entree, "quantite_entree", "La quantité entrée", strict=False)
        exiger_positif_optionnel(self.quantite_produite, "quantite_produite", "La quantité produite")
        exiger_positif_optionnel(self.quantite_conforme, "quantite_conforme", "La quantité conforme")
        exiger_positif_optionnel(self.quantite_rejetee, "quantite_rejetee", "La quantité rejetée")
        if self.heure_debut and self.heure_fin and self.heure_fin <= self.heure_debut:
            raise ValidationError({"heure_fin": "L'heure de fin doit être postérieure à l'heure de début."})
        if self.quantite_produite is not None:
            total_controle = (self.quantite_conforme or 0) + (self.quantite_rejetee or 0)
            if total_controle > self.quantite_produite:
                raise ValidationError({"quantite_conforme": (
                    f"Conforme + rejeté ({total_controle}) dépasse la quantité produite ({self.quantite_produite})."
                )})


class SuiviEau(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
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
    saisi_par = models.ForeignKey(
        Utilisateur, verbose_name="Saisi par", on_delete=models.PROTECT,
        null=True, blank=True, related_name="suivis_eau_saisis",
        help_text="Traçabilité : renseigné automatiquement avec l'utilisateur connecté.",
    )

    class Meta:
        verbose_name = "Suivi de l'eau"
        verbose_name_plural = "Suivis de l'eau"

    def __str__(self):
        return f"Suivi eau - {self.ordre_fabrication.numero}"

    def clean(self):
        """Chaque étape du flux ne peut pas recevoir plus d'eau que l'étape précédente n'en a fourni (§5.9)."""
        self.controler_of_en_production()
        exiger_positif(self.volume_capte_l, "volume_capte_l", "Le volume capté", strict=False)
        exiger_positif_optionnel(self.volume_envoye_traitement_l, "volume_envoye_traitement_l", "Le volume envoyé au traitement")
        exiger_positif(self.volume_obtenu_traitement_l, "volume_obtenu_traitement_l", "Le volume obtenu après traitement", strict=False)
        exiger_positif(self.volume_envoye_embouteillage_l, "volume_envoye_embouteillage_l", "Le volume envoyé à l'embouteillage", strict=False)
        entree_traitement = self.volume_capte_l
        if self.volume_envoye_traitement_l is not None:
            if self.volume_envoye_traitement_l > self.volume_capte_l:
                raise ValidationError({"volume_envoye_traitement_l": "Le volume envoyé au traitement dépasse le volume capté."})
            entree_traitement = self.volume_envoye_traitement_l
        if self.volume_obtenu_traitement_l > entree_traitement:
            raise ValidationError({"volume_obtenu_traitement_l": "Le volume obtenu après traitement dépasse le volume entré en traitement."})
        if self.volume_envoye_embouteillage_l > self.volume_obtenu_traitement_l:
            raise ValidationError({"volume_envoye_embouteillage_l": "Le volume envoyé à l'embouteillage dépasse le volume obtenu après traitement."})
        if self.bouteilles_conformes is not None and self.bouteilles_produites is not None:
            if self.bouteilles_conformes + (self.bouteilles_rejetees or 0) > self.bouteilles_produites:
                raise ValidationError({"bouteilles_conformes": "Bouteilles conformes + rejetées dépasse le nombre de bouteilles produites."})

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
    """Étapes historiques (avant le socle) : conservées pour la compatibilité. La liste
    de référence est désormais le paramétrage industriel (EtapeStandard)."""
    CAPTAGE = "CAPTAGE", "Captage"
    TRAITEMENT = "TRAITEMENT", "Traitement"
    SOUFFLAGE = "SOUFFLAGE", "Soufflage"
    EMBOUTEILLAGE = "EMBOUTEILLAGE", "Embouteillage"
    ETIQUETAGE = "ETIQUETAGE", "Étiquetage"
    CONDITIONNEMENT = "CONDITIONNEMENT", "Conditionnement"


# Anciens codes d'étape -> codes du circuit de référence.
ALIAS_ETAPES = {"EMBOUTEILLAGE": "REMPLISSAGE"}


class EtapeProduction(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
    """Suivi de la production étape par étape (processus de fabrication de la fiche technique)."""
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.CASCADE, related_name="etapes",
    )
    etape = models.CharField(
        "Étape", max_length=30,
        help_text="Code d'une étape du paramétrage (CAPTAGE, PREPARATION, REMPLISSAGE...) ; "
                  "si l'OF a un circuit, une étape de ce circuit.",
    )
    agent = models.ForeignKey(Utilisateur, verbose_name="Agent Production", on_delete=models.PROTECT)
    poste = models.ForeignKey("industriel.Poste", verbose_name="Poste", on_delete=models.PROTECT, null=True, blank=True)
    equipement = models.ForeignKey("industriel.Equipement", verbose_name="Machine", on_delete=models.PROTECT, null=True, blank=True)
    quantite_entree = models.DecimalField("Quantité entrée", max_digits=12, decimal_places=3, null=True, blank=True)
    quantite_produite = models.DecimalField(
        "Quantité produite à cette étape", max_digits=12, decimal_places=3,
        null=True, blank=True,
    )
    quantite_rejetee = models.DecimalField("Quantité rejetée", max_digits=12, decimal_places=3, null=True, blank=True)
    date_debut = models.DateTimeField("Début", null=True, blank=True)
    date_fin = models.DateTimeField("Fin", null=True, blank=True)
    duree_arret_min = models.DecimalField("Arrêts (minutes)", max_digits=8, decimal_places=1, null=True, blank=True)
    heures_machine = models.DecimalField(
        "Heures machine", max_digits=8, decimal_places=2, null=True, blank=True,
        help_text="Compteur d'heures ; vide = durée début -> fin moins les arrêts.",
    )
    energie_kwh = models.DecimalField("Énergie consommée (kWh)", max_digits=12, decimal_places=2, null=True, blank=True)
    energie_mesuree = models.BooleanField(
        "kWh relevés sur un compteur", default=False,
        help_text="Décoché = valeur estimée (jamais présentée comme une mesure).",
    )
    observations = models.TextField("Observations", blank=True)

    class Meta:
        verbose_name = "Étape de production"
        verbose_name_plural = "Étapes de production"
        ordering = ["ordre_fabrication", "date_debut"]

    def __str__(self):
        return f"{self.ordre_fabrication.numero} - {self.get_etape_display()}"

    def clean(self):
        self.controler_of_en_production()
        self.etape = ALIAS_ETAPES.get((self.etape or "").upper(), (self.etape or "").upper())
        for champ, libelle in (
            ("quantite_entree", "La quantité entrée"), ("quantite_produite", "La quantité produite"),
            ("quantite_rejetee", "La quantité rejetée"), ("duree_arret_min", "La durée d'arrêt"),
            ("heures_machine", "Les heures machine"), ("energie_kwh", "L'énergie consommée"),
        ):
            exiger_positif_optionnel(getattr(self, champ), champ, libelle)
        exiger_ordre_dates(self.date_debut, self.date_fin, "date_fin", "le début", "La fin")
        if self.quantite_entree is not None and self.quantite_produite is not None \
                and self.quantite_produite > self.quantite_entree:
            raise ValidationError({"quantite_produite": "La quantité produite ne peut pas dépasser la quantité entrée."})
        if self.energie_mesuree and self.energie_kwh is None:
            raise ValidationError({"energie_kwh": "Indiquez les kWh relevés sur le compteur."})
        from apps.industriel.models import EtapeStandard
        etape = EtapeStandard.objects.filter(code=self.etape, actif=True).first()
        if etape is None:
            raise ValidationError({"etape": f"Étape « {self.etape} » inconnue du paramétrage industriel."})
        of = self.ordre_fabrication if self.ordre_fabrication_id else None
        if of and of.circuit_id and not of.circuit.etapes.filter(etape__code=self.etape).exists():
            raise ValidationError({"etape": f"L'étape {etape.libelle} ne fait pas partie du circuit {of.circuit.code} de l'OF."})
        if self.poste_id:
            if self.poste.etape_id != etape.pk:
                raise ValidationError({"poste": f"Le poste {self.poste.code} ne réalise pas l'étape {etape.libelle}."})
            if of and of.ligne_id and self.poste.ligne_id != of.ligne_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} n'est pas sur la ligne de l'OF."})
        if self.equipement_id:
            if self.poste_id and self.equipement.poste_id and self.equipement.poste_id != self.poste_id:
                raise ValidationError({"equipement": f"La machine {self.equipement.code} n'est pas affectée à ce poste."})
            if of and of.activite and self.equipement.activite_id and self.equipement.activite_id != of.activite.pk:
                raise ValidationError({"equipement": f"La machine {self.equipement.code} est dédiée à une autre activité."})

    @property
    def heures_machine_effectives(self):
        """Heures machine saisies, sinon durée (fin - début - arrêts) ; None si inconnues."""
        from decimal import Decimal
        if self.heures_machine is not None:
            return Decimal(self.heures_machine)
        if self.date_debut and self.date_fin:
            heures = Decimal((self.date_fin - self.date_debut).total_seconds()) / Decimal(3600)
            heures -= Decimal(self.duree_arret_min or 0) / Decimal(60)
            return max(heures, Decimal(0))
        return None


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


class NaturePerte(models.TextChoices):
    """Les pertes sont des coûts identifiés (documents de coûts) : on les isole par nature."""
    PREFORMES_REJETEES = "PREFORMES_REJETEES", "Préformes rejetées (soufflage)"
    SUR_REMPLISSAGE = "SUR_REMPLISSAGE", "Sur-remplissage"
    REBUT_REMPLISSAGE = "REBUT_REMPLISSAGE", "Rebuts de remplissage"
    ETIQUETTES = "ETIQUETTES", "Étiquettes perdues"
    FILM = "FILM", "Film perdu (plastification)"
    PACKS_NON_CONFORMES = "PACKS_NON_CONFORMES", "Packs non conformes"
    CONCENTRE_REJETE = "CONCENTRE_REJETE", "Concentré rejeté (osmose)"
    EAU = "EAU", "Perte d'eau"
    PRODUIT_DEMARRAGE = "PRODUIT_DEMARRAGE", "Produits / rebuts de démarrage (changement de série)"
    CASSE_STOCKAGE = "CASSE_STOCKAGE", "Casse en stockage"
    AUTRE = "AUTRE", "Autre"


class PerteProduction(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
    """Pertes et rebuts constatés en cours de production (§5.11), valorisés quand la matière est connue."""
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
    nature = models.CharField("Nature de la perte", max_length=30, choices=NaturePerte.choices, default=NaturePerte.AUTRE)
    etape_code = models.CharField("Étape (code)", max_length=30, blank=True, help_text="Ex : SOUFFLAGE, REMPLISSAGE.")
    matiere = models.ForeignKey(
        Article, verbose_name="Matière / emballage perdu", on_delete=models.PROTECT, null=True, blank=True,
        related_name="pertes", help_text="Permet de valoriser la perte au coût moyen (CMUP).",
    )
    valeur = models.DecimalField("Valeur de la perte", max_digits=16, decimal_places=2, null=True, blank=True, editable=False)
    observations = models.TextField("Observations", blank=True)
    saisi_par = models.ForeignKey(
        Utilisateur, verbose_name="Saisi par", on_delete=models.PROTECT,
        null=True, blank=True, related_name="pertes_saisies",
        help_text="Traçabilité : renseigné automatiquement avec l'utilisateur connecté.",
    )
    date_constat = models.DateTimeField("Date du constat", auto_now_add=True)

    class Meta:
        verbose_name = "Perte de production"
        verbose_name_plural = "Pertes de production"

    def __str__(self):
        return f"Perte {self.quantite_perte} sur {self.ordre_fabrication.numero} ({self.get_motif_display()})"

    def clean(self):
        self.controler_of_en_production()
        exiger_positif(self.quantite_perte, "quantite_perte", "La quantité perdue")
        exiger_pourcentage(self.taux_perte, "taux_perte", "Le taux de perte")
        if self.etape_id and self.ordre_fabrication_id and self.etape.ordre_fabrication_id != self.ordre_fabrication_id:
            raise ValidationError({"etape": "Cette étape appartient à un autre OF."})
        if self.etape_id and not self.etape_code:
            self.etape_code = self.etape.etape
        if self.etape_code:
            from apps.industriel.models import EtapeStandard
            self.etape_code = ALIAS_ETAPES.get(self.etape_code.upper(), self.etape_code.upper())
            if not EtapeStandard.objects.filter(code=self.etape_code).exists():
                raise ValidationError({"etape_code": f"Étape « {self.etape_code} » inconnue du paramétrage industriel."})
        self.valoriser()

    def valoriser(self):
        """Valeur = quantité x coût moyen (CMUP) de la matière perdue ; vide si la matière n'est pas précisée."""
        from decimal import Decimal
        if not self.matiere_id or self.quantite_perte is None:
            self.valeur = None
            return
        from apps.stocks.models import ValorisationArticle
        cmup = ValorisationArticle.objects.filter(article_id=self.matiere_id).values_list("cout_unitaire_moyen", flat=True).first()
        self.valeur = (Decimal(self.quantite_perte) * Decimal(cmup or 0)).quantize(Decimal("0.01"))


class ConsommationLotMatiere(models.Model):
    """Traçabilité amont : quel lot de matière a servi à quelle sortie (donc à quel OF), et combien."""
    sortie = models.ForeignKey(SortieMatiere, verbose_name="Sortie matière", on_delete=models.PROTECT, related_name="consommations_lots")
    lot = models.ForeignKey("stocks.LotMatiere", verbose_name="Lot matière", on_delete=models.PROTECT, related_name="consommations")
    quantite = models.DecimalField("Quantité consommée", max_digits=14, decimal_places=4)
    quantite_retournee = models.DecimalField("Quantité retournée", max_digits=14, decimal_places=4, default=0)

    class Meta:
        verbose_name = "Consommation de lot matière"
        verbose_name_plural = "Consommations de lots matières"

    def __str__(self):
        return f"{self.lot.numero} -> {self.sortie.ordre_fabrication.numero} : {self.quantite}"

    @property
    def quantite_nette(self):
        return self.quantite - self.quantite_retournee


class ChangementSerie(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
    """
    Changement de série (format ou produit) : événement chiffré à part
    (documents de coûts) - temps d'arrêt, nettoyage, réglage, essais et
    rebuts de démarrage. Déclenche les contrôles « après changement de série ».
    """
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="OF démarré après le changement", on_delete=models.PROTECT,
        related_name="changements_serie",
    )
    article_precedent = models.ForeignKey(
        Article, verbose_name="Produit / format précédent", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    ligne = models.ForeignKey("industriel.Ligne", verbose_name="Ligne", on_delete=models.PROTECT, null=True, blank=True)
    date_debut = models.DateTimeField("Début")
    date_fin = models.DateTimeField("Fin", null=True, blank=True)
    duree_arret_min = models.DecimalField("Temps d'arrêt (min)", max_digits=8, decimal_places=1, default=0)
    duree_nettoyage_min = models.DecimalField("Nettoyage (min)", max_digits=8, decimal_places=1, default=0)
    duree_reglage_min = models.DecimalField("Réglage (min)", max_digits=8, decimal_places=1, default=0)
    quantite_essais = models.DecimalField("Quantité consommée en essais", max_digits=12, decimal_places=3, default=0)
    rebuts_demarrage = models.DecimalField("Rebuts de démarrage", max_digits=12, decimal_places=3, default=0)
    cout_nettoyage = models.DecimalField(
        "Coût réel du nettoyage", max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Produits de nettoyage, intervention... si connu.",
    )
    observations = models.TextField("Observations", blank=True)
    saisi_par = models.ForeignKey(Utilisateur, verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = "Changement de série"
        verbose_name_plural = "Changements de série"
        ordering = ["-date_debut"]

    def __str__(self):
        return f"Changement de série {self.ordre_fabrication.numero} ({self.date_debut:%Y-%m-%d %H:%M})"

    def clean(self):
        self.controler_of()
        if self.ordre_fabrication_id and self.ordre_fabrication.statut in ("BROUILLON",):
            raise ValidationError({"ordre_fabrication": "L'OF doit être lancé pour enregistrer un changement de série."})
        for champ in ("duree_arret_min", "duree_nettoyage_min", "duree_reglage_min", "quantite_essais", "rebuts_demarrage"):
            exiger_positif(getattr(self, champ), champ, "Cette valeur", strict=False)
        exiger_positif_optionnel(self.cout_nettoyage, "cout_nettoyage", "Le coût du nettoyage")
        exiger_ordre_dates(self.date_debut, self.date_fin, "date_fin", "le début", "La fin")
        if self.ordre_fabrication_id and not self.ligne_id:
            self.ligne = self.ordre_fabrication.ligne
        if self.ligne_id and self.ordre_fabrication_id and self.ordre_fabrication.ligne_id \
                and self.ligne_id != self.ordre_fabrication.ligne_id:
            raise ValidationError({"ligne": "La ligne du changement de série doit être celle de l'OF."})

    def save(self, *args, **kwargs):
        creation = self._state.adding
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creation:
                from apps.qualite.models import generer_controles
                generer_controles(self.ordre_fabrication, declencheurs=("CHANGEMENT_SERIE",))


class ParametreProduction(models.Model):
    """Règles de production configurables (une seule ligne)."""
    bloquer_lancement_stock_insuffisant = models.BooleanField(
        "Bloquer le lancement d'un OF si le stock est insuffisant", default=True,
        help_text="Décoché : le lancement est seulement signalé (avertissement).",
    )
    controle_qualite_bloque_cloture = models.BooleanField(
        "Bloquer la clôture si des contrôles bloquants manquent ou sont non conformes", default=True,
    )

    class Meta:
        verbose_name = "Paramètres de production"
        verbose_name_plural = "Paramètres de production"

    def __str__(self):
        return "Paramètres de production"

    @classmethod
    def courant(cls):
        parametre, _ = cls.objects.get_or_create(pk=1)
        return parametre
