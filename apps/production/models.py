

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
        if self.statut == StatutPlanProduction.ANNULEE:
            raise ValueError("Cette prévision est annulée : elle ne peut pas être convertie en OF.")
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
            if self.article.type_article == "MATIERE_PREMIERE":
                raise ValidationError({"article": "On ne fabrique pas une matière première : choisissez un produit fini ou intermédiaire."})

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

    def _creer_mouvement_sortie(self):
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        MouvementStock.objects.create(
            article=self.matiere,
            depot=depot_par_defaut("Magasin principal"),
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
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        MouvementStock.objects.create(
            article=self.matiere,
            depot=depot_par_defaut("Magasin principal"),
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

    class Meta:
        verbose_name = "Suivi de production"
        verbose_name_plural = "Suivis de production"
        ordering = ["-date", "-heure_debut"]

    def __str__(self):
        return f"{self.ordre_fabrication.numero} - {self.date} {self.heure_debut}"

    def clean(self):
        self.controler_of()
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

    class Meta:
        verbose_name = "Suivi de l'eau"
        verbose_name_plural = "Suivis de l'eau"

    def __str__(self):
        return f"Suivi eau - {self.ordre_fabrication.numero}"

    def clean(self):
        """Chaque étape du flux ne peut pas recevoir plus d'eau que l'étape précédente n'en a fourni (§5.9)."""
        self.controler_of()
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
    CAPTAGE = "CAPTAGE", "Captage"
    TRAITEMENT = "TRAITEMENT", "Traitement"
    SOUFFLAGE = "SOUFFLAGE", "Soufflage"
    EMBOUTEILLAGE = "EMBOUTEILLAGE", "Embouteillage"
    ETIQUETAGE = "ETIQUETAGE", "Étiquetage"
    CONDITIONNEMENT = "CONDITIONNEMENT", "Conditionnement"


class EtapeProduction(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        self.controler_of()
        exiger_positif_optionnel(self.quantite_produite, "quantite_produite", "La quantité produite")
        exiger_ordre_dates(self.date_debut, self.date_fin, "date_fin", "le début", "La fin")


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


class PerteProduction(SaisieSurOFMixin, ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        self.controler_of()
        exiger_positif(self.quantite_perte, "quantite_perte", "La quantité perdue")
        exiger_pourcentage(self.taux_perte, "taux_perte", "Le taux de perte")
        if self.etape_id and self.ordre_fabrication_id and self.etape.ordre_fabrication_id != self.ordre_fabrication_id:
            raise ValidationError({"etape": "Cette étape appartient à un autre OF."})
