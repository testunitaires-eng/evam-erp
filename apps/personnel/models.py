"""
Module Personnel / main-d'œuvre - phase 1 : registre et affectations.

Les OUVRIERS sont les personnes qui travaillent aux étapes de
production (soufflage, remplissage, conditionnement, nettoyage...).
Ils n'ont JAMAIS accès à l'application : ce ne sont pas des
Utilisateur (comptes de connexion), mais de simples fiches, tenues par
le Responsable Production / l'Administrateur SI.

- Ouvrier : la fiche (matricule automatique), permanent ou temporaire
  (un temporaire a obligatoirement une date de fin de contrat), et ses
  ZONES DE COMPÉTENCE : les étapes du processus qu'il sait tenir
  (EtapeStandard du socle industriel, paramétrable : on peut y ajouter
  des fonctions hors ligne comme « Nettoyage » ou « Magasin »).
- Affectation : l'ouvrier placé sur une étape (et éventuellement un
  poste précis d'une ligne) pour une période, ou dans l'équipe d'un OF.
  Contrôles : ouvrier actif et sous contrat sur toute la période,
  compétent pour l'étape, pas deux postes en même temps.

- ConditionRemuneration : salaire mensuel fixe ou taux journalier, et
  périodicité de paie (hebdomadaire / mensuelle), historisés par date
  d'effet (une augmentation ne change pas les périodes passées).
- Pointage : une ligne par ouvrier et par jour (présent, demi-journée,
  absent, absence justifiée ou non), rattachée à l'étape / au poste /
  à l'OF de son affectation. Saisi puis validé par le RH ; un pointage
  validé ne change plus.

- EtatPaie : la paie d'un ouvrier pour une période (semaine du lundi au
  dimanche, ou mois civil), calculée jour par jour sur les pointages
  validés. Préparé par le RH -> validé par la DAF (écriture D 661 / C 422,
  coût de main-d'œuvre des OF) -> payé en espèces par le caissier
  (décaissement de caisse, écriture D 422 / C 571).
"""

import calendar
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.comptes.models import Utilisateur
from apps.core.models import generer_code_unique
from apps.core.validation import ValidationAvantEnregistrement, valeur_en_base


class TypeContrat(models.TextChoices):
    PERMANENT = "PERMANENT", "Permanent (personnel EVAM)"
    TEMPORAIRE = "TEMPORAIRE", "Temporaire (période déterminée)"


class TypePiece(models.TextChoices):
    CNI = "CNI", "Carte nationale d'identité"
    PASSEPORT = "PASSEPORT", "Passeport"
    CARTE_SEJOUR = "CARTE_SEJOUR", "Carte de séjour"
    AUTRE = "AUTRE", "Autre"


def periodes_se_chevauchent(debut1, fin1, debut2, fin2):
    """Deux périodes [début, fin] (fin vide = sans fin) ont-elles au moins un jour en commun ?"""
    return (fin2 is None or debut1 <= fin2) and (fin1 is None or debut2 <= fin1)


class Ouvrier(ValidationAvantEnregistrement, models.Model):
    """Une personne qui travaille dans le processus de production, sans accès à l'application."""
    matricule = models.CharField(
        "Matricule", max_length=30, unique=True, editable=False,
        help_text="Généré automatiquement (OUV-000001...), jamais saisi.",
    )
    nom = models.CharField("Nom", max_length=100)
    prenom = models.CharField("Prénom(s)", max_length=150)
    date_naissance = models.DateField("Date de naissance", null=True, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    adresse = models.CharField("Adresse / quartier", max_length=255, blank=True)
    type_piece = models.CharField("Type de pièce d'identité", max_length=15, choices=TypePiece.choices, blank=True)
    numero_piece = models.CharField("N° de pièce d'identité", max_length=50, blank=True)

    type_contrat = models.CharField("Type de contrat", max_length=15, choices=TypeContrat.choices)
    date_entree = models.DateField("Date d'entrée", help_text="Début du contrat (ou de la mission pour un temporaire).")
    date_fin_contrat = models.DateField(
        "Fin de contrat", null=True, blank=True,
        help_text="Obligatoire pour un temporaire. Pour un permanent : date de départ prévue, sinon vide.",
    )
    usine = models.ForeignKey(
        "industriel.Usine", verbose_name="Site de rattachement", on_delete=models.PROTECT,
        null=True, blank=True, related_name="ouvriers",
    )
    competences = models.ManyToManyField(
        "industriel.EtapeStandard", verbose_name="Zones de compétence", blank=True, related_name="ouvriers_competents",
        help_text="Étapes du processus que l'ouvrier sait tenir : il ne peut être affecté qu'à celles-ci.",
    )
    actif = models.BooleanField("Actif", default=True, help_text="Décocher au départ de l'ouvrier (la fiche est conservée).")
    motif_sortie = models.CharField("Motif de sortie", max_length=255, blank=True)
    observations = models.TextField("Observations", blank=True)
    date_creation = models.DateTimeField("Créé le", auto_now_add=True)

    class Meta:
        verbose_name = "Ouvrier"
        verbose_name_plural = "Ouvriers"
        ordering = ["nom", "prenom"]

    def __str__(self):
        return f"{self.matricule} - {self.nom_complet}"

    @property
    def nom_complet(self):
        return f"{self.nom} {self.prenom}".strip()

    def est_sous_contrat(self, date=None):
        """Actif et dans sa période de contrat à cette date (aujourd'hui par défaut)."""
        date = date or timezone.localdate()
        return bool(
            self.actif and self.date_entree and self.date_entree <= date
            and (self.date_fin_contrat is None or date <= self.date_fin_contrat)
        )

    def save(self, *args, **kwargs):
        if not self.matricule:
            self.matricule = generer_code_unique(Ouvrier, "OUV", champ="matricule")
        desactivation = not self._state.adding and not self.actif and valeur_en_base(self, "actif")
        with transaction.atomic():
            super().save(*args, **kwargs)
            if desactivation:
                self._clore_affectations()

    def _clore_affectations(self):
        """Départ : les affectations en cours s'arrêtent aujourd'hui, celles à venir sont retirées."""
        aujourdhui = timezone.localdate()
        for affectation in self.affectations.all():
            if affectation.date_debut > aujourdhui:
                affectation.delete()
            elif affectation.date_fin is None or affectation.date_fin > aujourdhui:
                affectation.date_fin = aujourdhui
                affectation.save(update_fields=["date_fin"])

    def clean(self):
        self.nom = (self.nom or "").strip().upper()
        self.prenom = (self.prenom or "").strip()
        if not self.nom:
            raise ValidationError({"nom": "Le nom est obligatoire."})
        if not self.prenom:
            raise ValidationError({"prenom": "Le prénom est obligatoire."})
        if self.type_contrat == TypeContrat.TEMPORAIRE and not self.date_fin_contrat:
            raise ValidationError({"date_fin_contrat": "Un ouvrier temporaire a obligatoirement une date de fin de contrat."})
        if self.date_entree and self.date_fin_contrat and self.date_fin_contrat < self.date_entree:
            raise ValidationError({"date_fin_contrat": "La fin de contrat ne peut pas précéder la date d'entrée."})
        self.numero_piece = (self.numero_piece or "").strip()
        if self.numero_piece and Ouvrier.objects.filter(
            type_piece=self.type_piece, numero_piece__iexact=self.numero_piece,
        ).exclude(pk=self.pk).exists():
            raise ValidationError({"numero_piece": "Un ouvrier est déjà enregistré avec cette pièce d'identité."})
        if not self.actif and not (self.motif_sortie or "").strip():
            raise ValidationError({"motif_sortie": "Indiquez le motif de sortie de l'ouvrier."})
        if self.pk and self.actif:
            self._verifier_affectations_dans_contrat()

    def _verifier_affectations_dans_contrat(self):
        """Raccourcir le contrat ne doit pas laisser d'affectation hors contrat."""
        hors_contrat = [
            a for a in self.affectations.all()
            if (self.date_entree and a.date_debut < self.date_entree)
            or (self.date_fin_contrat and (a.date_fin is None or a.date_fin > self.date_fin_contrat))
        ]
        if hors_contrat:
            raise ValidationError({"date_fin_contrat": (
                f"{len(hors_contrat)} affectation(s) sortent de la période de contrat "
                f"(ex : {hors_contrat[0]}) : modifiez-les d'abord."
            )})

    def condition_au(self, date):
        """Condition de rémunération en vigueur à cette date (la plus récente déjà entrée en vigueur)."""
        return self.conditions_remuneration.filter(date_effet__lte=date).order_by("-date_effet").first()

    def affectations_du(self, date):
        return [a for a in self.affectations.select_related("etape", "poste", "ordre_fabrication") if a.est_active(date)]

    def verifier_suppression(self):
        if self.affectations.exists() or self.pointages.exists():
            raise ValidationError("Cet ouvrier a déjà été affecté : désactivez-le (avec un motif de sortie) au lieu de le supprimer.")


class Affectation(ValidationAvantEnregistrement, models.Model):
    """
    Un ouvrier placé sur une zone du processus pour une période :
    - affectation à un poste / une étape (« il tient le remplissage de la
      ligne Eau 1 du 1er au 30 ») : un ouvrier n'occupe qu'un poste à la fois ;
    - affectation à un OF (« il fait partie de l'équipe de l'OF-000123 ») :
      période reprise du planning de l'OF si elle n'est pas saisie ; un
      même ouvrier peut travailler sur plusieurs OF.
    """
    ouvrier = models.ForeignKey(Ouvrier, verbose_name="Ouvrier", on_delete=models.PROTECT, related_name="affectations")
    etape = models.ForeignKey(
        "industriel.EtapeStandard", verbose_name="Étape / zone", on_delete=models.PROTECT, related_name="affectations_ouvriers",
        null=True, blank=True, help_text="Déduite du poste si un poste est choisi.",
    )
    poste = models.ForeignKey(
        "industriel.Poste", verbose_name="Poste", on_delete=models.PROTECT, null=True, blank=True,
        related_name="affectations_ouvriers", help_text="Poste précis d'une ligne (facultatif).",
    )
    ordre_fabrication = models.ForeignKey(
        "production.OrdreFabrication", verbose_name="OF", on_delete=models.CASCADE, null=True, blank=True,
        related_name="affectations_ouvriers", help_text="Vide = affectation au poste / à l'étape, hors OF précis.",
    )
    date_debut = models.DateField("Du", null=True, blank=True, help_text="Vide pour un OF = début planifié de l'OF.")
    date_fin = models.DateField(
        "Au", null=True, blank=True,
        help_text="Vide = sans fin prévue (permanent). Pour un temporaire, limitée à sa fin de contrat.",
    )
    observations = models.CharField("Observations", max_length=255, blank=True)
    affecte_par = models.ForeignKey(
        Utilisateur, verbose_name="Affecté par", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    date_creation = models.DateTimeField("Créée le", auto_now_add=True)

    class Meta:
        verbose_name = "Affectation d'ouvrier"
        verbose_name_plural = "Affectations d'ouvriers"
        ordering = ["-date_debut", "ouvrier__nom"]

    def __str__(self):
        cible = self.ordre_fabrication.numero if self.ordre_fabrication_id else (
            self.poste.code if self.poste_id else (self.etape.libelle if self.etape_id else "?")
        )
        return f"{self.ouvrier} -> {cible} ({self.date_debut} - {self.date_fin or '...'})"

    def est_active(self, date=None):
        date = date or timezone.localdate()
        return self.date_debut <= date and (self.date_fin is None or date <= self.date_fin)

    def _completer_depuis_of(self):
        of = self.ordre_fabrication
        if self.date_debut is None:
            self.date_debut = (
                timezone.localtime(of.date_debut_prevue).date() if of.date_debut_prevue
                else of.date_prevue or timezone.localdate()
            )
        if self.date_fin is None and of.date_fin_prevue:
            self.date_fin = timezone.localtime(of.date_fin_prevue).date()

    def clean(self):
        if self.pk and valeur_en_base(self, "ouvrier") != self.ouvrier_id:
            raise ValidationError({"ouvrier": "L'ouvrier d'une affectation ne change pas : créez une nouvelle affectation."})
        # Zone : le poste détermine l'étape.
        if self.poste_id:
            if self.etape_id and self.etape_id != self.poste.etape_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} correspond à l'étape « {self.poste.etape.libelle} »."})
            self.etape_id = self.poste.etape_id
        if not self.etape_id:
            raise ValidationError({"etape": "Choisissez l'étape (ou le poste) à laquelle l'ouvrier est affecté."})
        # OF : modifiable, même ligne, période reprise du planning.
        if self.ordre_fabrication_id:
            of = self.ordre_fabrication
            if of.est_verrouille:
                raise ValidationError({"ordre_fabrication": f"L'OF {of.numero} est {of.get_statut_display().lower()}."})
            if self.poste_id and of.ligne_id and self.poste.ligne_id != of.ligne_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} n'est pas sur la ligne de l'OF {of.numero}."})
            self._completer_depuis_of()
        if self.date_debut is None:
            raise ValidationError({"date_debut": "La date de début est obligatoire."})
        if not self.ouvrier_id:
            return
        ouvrier = self.ouvrier
        # Un temporaire sans date de fin saisie est affecté jusqu'à la fin de son contrat.
        if self.date_fin is None and ouvrier.date_fin_contrat:
            self.date_fin = ouvrier.date_fin_contrat
        if self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La date de fin ne peut pas précéder la date de début."})
        if not ouvrier.actif:
            raise ValidationError({"ouvrier": f"{ouvrier.nom_complet} n'est plus actif."})
        if self.date_debut < ouvrier.date_entree:
            raise ValidationError({"date_debut": f"{ouvrier.nom_complet} n'entre chez EVAM que le {ouvrier.date_entree:%d/%m/%Y}."})
        if ouvrier.date_fin_contrat and self.date_fin > ouvrier.date_fin_contrat:
            raise ValidationError({"date_fin": (
                f"Le contrat de {ouvrier.nom_complet} se termine le {ouvrier.date_fin_contrat:%d/%m/%Y}."
            )})
        if ouvrier.pk and not ouvrier.competences.filter(pk=self.etape_id).exists():
            raise ValidationError({"etape": (
                f"{ouvrier.nom_complet} n'a pas « {self.etape.libelle} » dans ses zones de compétence."
            )})
        if self.ordre_fabrication_id is None:
            for autre in Affectation.objects.filter(
                ouvrier_id=self.ouvrier_id, ordre_fabrication__isnull=True,
            ).exclude(pk=self.pk).select_related("etape", "poste"):
                if periodes_se_chevauchent(self.date_debut, self.date_fin, autre.date_debut, autre.date_fin):
                    raise ValidationError({"date_debut": (
                        f"{ouvrier.nom_complet} est déjà affecté sur cette période : {autre}."
                    )})


class ModeRemuneration(models.TextChoices):
    MENSUEL = "MENSUEL", "Salaire mensuel fixe"
    JOURNALIER = "JOURNALIER", "Taux journalier (par jour travaillé)"


class PeriodicitePaie(models.TextChoices):
    HEBDOMADAIRE = "HEBDOMADAIRE", "Hebdomadaire"
    MENSUELLE = "MENSUELLE", "Mensuelle"


class ConditionRemuneration(ValidationAvantEnregistrement, models.Model):
    """
    Combien et à quel rythme l'ouvrier est payé, à partir d'une date
    d'effet. On ne modifie pas une condition déjà appliquée à des
    pointages validés : on en crée une nouvelle (nouvelle date d'effet),
    pour que les périodes passées gardent le taux de l'époque.
    """
    ouvrier = models.ForeignKey(Ouvrier, verbose_name="Ouvrier", on_delete=models.PROTECT, related_name="conditions_remuneration")
    mode = models.CharField("Mode de rémunération", max_length=15, choices=ModeRemuneration.choices)
    montant = models.DecimalField(
        "Montant (FCFA)", max_digits=12, decimal_places=2,
        help_text="Salaire mensuel pour le mode mensuel, montant par jour travaillé pour le mode journalier.",
    )
    periodicite_paie = models.CharField("Paie", max_length=15, choices=PeriodicitePaie.choices, default=PeriodicitePaie.MENSUELLE)
    date_effet = models.DateField("En vigueur à partir du")
    saisi_par = models.ForeignKey(Utilisateur, verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_creation = models.DateTimeField("Créée le", auto_now_add=True)

    class Meta:
        verbose_name = "Condition de rémunération"
        verbose_name_plural = "Conditions de rémunération"
        ordering = ["ouvrier", "-date_effet"]
        unique_together = ("ouvrier", "date_effet")

    def __str__(self):
        return f"{self.ouvrier} : {self.montant} ({self.get_mode_display()}) dès le {self.date_effet:%d/%m/%Y}"

    def _pointages_valides_couverts(self, date_effet=None):
        """Pointages validés auxquels cette condition s'applique (jusqu'à la condition suivante)."""
        date_effet = date_effet or self.date_effet
        suivante = ConditionRemuneration.objects.filter(
            ouvrier_id=self.ouvrier_id, date_effet__gt=date_effet,
        ).exclude(pk=self.pk).order_by("date_effet").first()
        pointages = Pointage.objects.filter(ouvrier_id=self.ouvrier_id, date__gte=date_effet, statut=StatutPointage.VALIDE)
        if suivante:
            pointages = pointages.filter(date__lt=suivante.date_effet)
        return pointages

    def clean(self):
        if self.montant is None or self.montant <= 0:
            raise ValidationError({"montant": "Le montant doit être strictement positif."})
        if self.ouvrier_id and self.date_effet:
            ouvrier = self.ouvrier
            paie = paie_arretee(self.ouvrier_id, self.date_effet, jusqu_a_la_fin=True)
            if paie:
                raise ValidationError({"date_effet": (
                    f"La paie de {ouvrier.nom_complet} est déjà arrêtée jusqu'au {paie.date_fin:%d/%m/%Y} ({paie.numero}) : "
                    "choisissez une date d'effet postérieure."
                )})
            if self.date_effet < ouvrier.date_entree:
                raise ValidationError({"date_effet": f"{ouvrier.nom_complet} n'entre chez EVAM que le {ouvrier.date_entree:%d/%m/%Y}."})
            if ouvrier.date_fin_contrat and self.date_effet > ouvrier.date_fin_contrat:
                raise ValidationError({"date_effet": f"Le contrat de {ouvrier.nom_complet} se termine le {ouvrier.date_fin_contrat:%d/%m/%Y}."})
        if self.pk:
            if valeur_en_base(self, "ouvrier") != self.ouvrier_id:
                raise ValidationError({"ouvrier": "L'ouvrier d'une condition ne change pas."})
            ancienne_date = valeur_en_base(self, "date_effet")
            modifiee = any(valeur_en_base(self, champ) != getattr(self, champ)
                           for champ in ("mode", "montant", "periodicite_paie", "date_effet"))
            if modifiee and self._pointages_valides_couverts(ancienne_date).exists():
                raise ValidationError(
                    "Cette condition s'applique déjà à des pointages validés : créez une nouvelle condition "
                    "avec une nouvelle date d'effet au lieu de la modifier."
                )

    def verifier_suppression(self):
        if self._pointages_valides_couverts().exists() or paie_arretee(self.ouvrier_id, self.date_effet, jusqu_a_la_fin=True):
            raise ValidationError("Cette condition s'applique déjà à des pointages validés ou à une paie arrêtée : elle ne peut pas être supprimée.")


def paie_arretee(ouvrier_id, date, jusqu_a_la_fin=False):
    """
    État de paie validé ou payé couvrant `date` (ou, si jusqu_a_la_fin,
    se terminant à partir de `date`) : la période est arrêtée, ses
    pointages et taux ne changent plus.
    """
    etats = EtatPaie.objects.filter(
        ouvrier_id=ouvrier_id, statut__in=(StatutEtatPaie.VALIDE, StatutEtatPaie.PAYE), date_fin__gte=date,
    )
    if not jusqu_a_la_fin:
        etats = etats.filter(date_debut__lte=date)
    return etats.order_by("-date_fin").first()


class Presence(models.TextChoices):
    PRESENT = "PRESENT", "Présent"
    DEMI_JOURNEE = "DEMI_JOURNEE", "Demi-journée"
    ABSENT = "ABSENT", "Absent"


class StatutPointage(models.TextChoices):
    SAISI = "SAISI", "Saisi"
    VALIDE = "VALIDE", "Validé"


# Part de journée travaillée selon la présence (sert au calcul de la paie et des coûts).
FRACTION_JOUR = {Presence.PRESENT: Decimal("1"), Presence.DEMI_JOURNEE: Decimal("0.5"), Presence.ABSENT: Decimal("0")}


class Pointage(ValidationAvantEnregistrement, models.Model):
    """
    La journée d'un ouvrier, pointée par le RH. Le lieu de travail
    (étape, poste, OF) est repris de son affectation du jour s'il n'est
    pas saisi ; l'OF est facultatif. Une absence peut être justifiée
    (congé, maladie...) : elle n'est alors pas retenue sur un salaire
    mensuel. Saisi -> Validé ; un pointage validé ne change plus.
    """
    ouvrier = models.ForeignKey(Ouvrier, verbose_name="Ouvrier", on_delete=models.PROTECT, related_name="pointages")
    date = models.DateField("Jour")
    presence = models.CharField("Présence", max_length=15, choices=Presence.choices, default=Presence.PRESENT)
    absence_justifiee = models.BooleanField(
        "Absence justifiée", default=False,
        help_text="Congé, maladie... : non retenue sur le salaire mensuel. Sans objet si présent.",
    )
    motif_absence = models.CharField("Motif de l'absence", max_length=255, blank=True)
    etape = models.ForeignKey(
        "industriel.EtapeStandard", verbose_name="Étape", on_delete=models.PROTECT, null=True, blank=True, related_name="pointages",
    )
    poste = models.ForeignKey("industriel.Poste", verbose_name="Poste", on_delete=models.PROTECT, null=True, blank=True, related_name="pointages")
    ordre_fabrication = models.ForeignKey(
        "production.OrdreFabrication", verbose_name="OF", on_delete=models.PROTECT, null=True, blank=True, related_name="pointages",
    )
    observations = models.CharField("Observations", max_length=255, blank=True)
    statut = models.CharField("Statut", max_length=10, choices=StatutPointage.choices, default=StatutPointage.SAISI)
    saisi_par = models.ForeignKey(Utilisateur, verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    valide_par = models.ForeignKey(Utilisateur, verbose_name="Validé par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_validation = models.DateTimeField("Validé le", null=True, blank=True)

    class Meta:
        verbose_name = "Pointage"
        verbose_name_plural = "Pointages"
        ordering = ["-date", "ouvrier__nom"]
        unique_together = ("ouvrier", "date")

    def __str__(self):
        return f"{self.ouvrier} le {self.date:%d/%m/%Y} : {self.get_presence_display()}"

    @property
    def fraction_jour(self):
        return FRACTION_JOUR[self.presence]

    def _completer_depuis_affectation(self):
        """Lieu de travail non saisi : celui de l'affectation du jour (un OF unique en priorité, sinon le poste)."""
        if self.etape_id or self.poste_id or self.ordre_fabrication_id or self.presence == Presence.ABSENT:
            return
        affectations = self.ouvrier.affectations_du(self.date)
        sur_of = [a for a in affectations if a.ordre_fabrication_id]
        choix = sur_of[0] if len(sur_of) == 1 else next((a for a in affectations if not a.ordre_fabrication_id), None)
        if choix is not None:
            self.etape_id, self.poste_id, self.ordre_fabrication_id = choix.etape_id, choix.poste_id, choix.ordre_fabrication_id

    def clean(self):
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutPointage.VALIDE:
            raise ValidationError("Ce pointage est validé : il ne peut plus être modifié.")
        if self.statut == StatutPointage.VALIDE and ancien_statut is None:
            raise ValidationError({"statut": "Un pointage se saisit d'abord, puis se valide (action Valider)."})
        if self.pk and valeur_en_base(self, "ouvrier") != self.ouvrier_id:
            raise ValidationError({"ouvrier": "L'ouvrier d'un pointage ne change pas."})
        if not self.ouvrier_id or not self.date:
            return
        ouvrier = self.ouvrier
        paie = paie_arretee(self.ouvrier_id, self.date)
        if paie:
            raise ValidationError({"date": f"La paie de {ouvrier.nom_complet} est déjà {paie.get_statut_display().lower()} pour ce jour ({paie.numero})."})
        if self.date > timezone.localdate():
            raise ValidationError({"date": "On ne pointe pas un jour à venir."})
        if self.date < ouvrier.date_entree or (ouvrier.date_fin_contrat and self.date > ouvrier.date_fin_contrat):
            raise ValidationError({"date": f"{ouvrier.nom_complet} n'est pas sous contrat le {self.date:%d/%m/%Y}."})
        if not ouvrier.actif and self._state.adding:
            raise ValidationError({"ouvrier": f"{ouvrier.nom_complet} n'est plus actif : pointez ses jours avant de désactiver sa fiche."})
        if self.presence == Presence.PRESENT:
            self.absence_justifiee, self.motif_absence = False, ""
        elif self.absence_justifiee and not (self.motif_absence or "").strip():
            raise ValidationError({"motif_absence": "Indiquez le motif de l'absence justifiée."})
        if self.presence == Presence.ABSENT:
            self.etape_id = self.poste_id = self.ordre_fabrication_id = None
            return
        self._completer_depuis_affectation()
        if self.poste_id:
            if self.etape_id and self.etape_id != self.poste.etape_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} correspond à l'étape « {self.poste.etape.libelle} »."})
            self.etape_id = self.poste.etape_id
        if self.ordre_fabrication_id:
            of = self.ordre_fabrication
            if of.statut == "ANNULE":
                raise ValidationError({"ordre_fabrication": f"L'OF {of.numero} est annulé."})
            if not any(a.ordre_fabrication_id == of.pk for a in ouvrier.affectations_du(self.date)):
                raise ValidationError({"ordre_fabrication": (
                    f"{ouvrier.nom_complet} n'est pas affecté à l'OF {of.numero} le {self.date:%d/%m/%Y}."
                )})

    def verifier_suppression(self):
        if self.statut == StatutPointage.VALIDE:
            raise ValidationError("Un pointage validé ne peut pas être supprimé.")

    def valider(self, utilisateur):
        if self.statut == StatutPointage.VALIDE:
            raise ValueError(f"Le pointage de {self.ouvrier.nom_complet} du {self.date:%d/%m/%Y} est déjà validé.")
        self.statut = StatutPointage.VALIDE
        self.valide_par = utilisateur
        self.date_validation = timezone.now()
        # Mise à jour ciblée : pas de nouveau contrôle de saisie ; l'historique
        # du changement de statut est enregistré par ValidationAvantEnregistrement.
        self.save(update_fields=["statut", "valide_par", "date_validation"])


# --- Paie ---------------------------------------------------------------------

HEURES_PAR_JOUR = Decimal("8")      # journée standard : convertit les jours pointés en heures pour les coûts des OF
JOURS_OUVRABLES = range(0, 5)        # du lundi (0) au vendredi (4)


def periode_de_paie(periodicite, jour):
    """Période contenant `jour` : semaine du lundi au dimanche, ou mois civil."""
    if periodicite == PeriodicitePaie.HEBDOMADAIRE:
        debut = jour - timedelta(days=jour.weekday())
        return debut, debut + timedelta(days=6)
    return jour.replace(day=1), jour.replace(day=calendar.monthrange(jour.year, jour.month)[1])


def jours_ouvrables_du_mois(jour):
    debut, fin = periode_de_paie(PeriodicitePaie.MENSUELLE, jour)
    return sum(1 for n in range((fin - debut).days + 1) if (debut + timedelta(days=n)).weekday() in JOURS_OUVRABLES)


class StatutEtatPaie(models.TextChoices):
    BROUILLON = "BROUILLON", "Préparé (RH)"
    VALIDE = "VALIDE", "Validé (DAF)"
    PAYE = "PAYE", "Payé"
    ANNULE = "ANNULE", "Annulé"


class EtatPaie(ValidationAvantEnregistrement, models.Model):
    """
    Ce qui est dû à un ouvrier pour une période, calculé JOUR PAR JOUR
    avec la condition de rémunération en vigueur ce jour-là :
    - taux journalier : taux x part de journée pointée (présent 1,
      demi-journée 0,5), week-end compris s'il a travaillé ;
    - salaire mensuel : chaque jour ouvrable (lundi-vendredi) sous contrat
      vaut salaire / jours ouvrables du mois, moins la part d'absence non
      justifiée ; un jour ouvrable non pointé est payé (salaire fixe) mais
      signalé (jours_non_pointes). Entrée / sortie en cours de mois :
      seuls les jours sous contrat comptent.
    Pas d'heures supplémentaires, de primes ni de charges sociales.
    Montant arrondi au franc. Tous les pointages de la période doivent
    être validés.
    """
    TRANSITIONS = {
        StatutEtatPaie.BROUILLON: {StatutEtatPaie.VALIDE},
        StatutEtatPaie.VALIDE: {StatutEtatPaie.PAYE, StatutEtatPaie.ANNULE},
    }

    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    ouvrier = models.ForeignKey(Ouvrier, verbose_name="Ouvrier", on_delete=models.PROTECT, related_name="etats_paie")
    periodicite = models.CharField("Paie", max_length=15, choices=PeriodicitePaie.choices)
    date_debut = models.DateField("Du")
    date_fin = models.DateField("Au")
    jours_travailles = models.DecimalField("Jours travaillés", max_digits=6, decimal_places=1, default=0, editable=False)
    jours_absence_retenus = models.DecimalField(
        "Jours d'absence retenus", max_digits=6, decimal_places=1, default=0, editable=False,
        help_text="Absences non justifiées retenues sur un salaire mensuel.",
    )
    jours_non_pointes = models.PositiveIntegerField(
        "Jours ouvrables non pointés", default=0, editable=False,
        help_text="Salaire mensuel : jours payés faute de pointage (à vérifier).",
    )
    montant = models.DecimalField("Montant à payer (FCFA)", max_digits=12, decimal_places=2, default=0, editable=False)
    statut = models.CharField("Statut", max_length=12, choices=StatutEtatPaie.choices, default=StatutEtatPaie.BROUILLON)
    prepare_par = models.ForeignKey(Utilisateur, verbose_name="Préparé par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    valide_par = models.ForeignKey(Utilisateur, verbose_name="Validé par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_validation = models.DateTimeField("Validé le", null=True, blank=True)
    decaissement = models.OneToOneField(
        "caisse.Decaissement", verbose_name="Décaissement (paiement)", on_delete=models.PROTECT,
        null=True, blank=True, related_name="etat_paie",
    )
    date_paiement = models.DateTimeField("Payé le", null=True, blank=True)
    motif_annulation = models.CharField("Motif d'annulation", max_length=255, blank=True)
    date_creation = models.DateTimeField("Préparé le", auto_now_add=True)

    class Meta:
        verbose_name = "État de paie"
        verbose_name_plural = "États de paie"
        ordering = ["-date_debut", "ouvrier__nom"]

    def __str__(self):
        return f"{self.numero} - {self.ouvrier.nom_complet} ({self.date_debut:%d/%m/%Y} - {self.date_fin:%d/%m/%Y})"

    # -- calcul ----------------------------------------------------------------
    def calculer(self):
        """
        Met à jour jours et montant ; retourne la répartition par OF
        {of_id: [jours, montant]} des jours pointés sur un OF.
        """
        ouvrier = self.ouvrier
        debut = max(self.date_debut, ouvrier.date_entree)
        fin = min(self.date_fin, ouvrier.date_fin_contrat or self.date_fin)
        pointages = {p.date: p for p in ouvrier.pointages.filter(date__gte=debut, date__lte=fin)}
        non_valides = sorted(d for d, p in pointages.items() if p.statut != StatutPointage.VALIDE)
        if non_valides:
            raise ValidationError(
                f"{ouvrier.nom_complet} : {len(non_valides)} pointage(s) non validé(s) sur la période "
                f"(dont le {non_valides[0]:%d/%m/%Y}) : validez-les d'abord."
            )
        conditions = list(ouvrier.conditions_remuneration.order_by("date_effet"))
        total, travailles, absences, non_pointes, par_of = Decimal(0), Decimal(0), Decimal(0), 0, {}
        jour = debut
        while jour <= fin:
            condition = next((c for c in reversed(conditions) if c.date_effet <= jour), None)
            pointage = pointages.get(jour)
            fraction = pointage.fraction_jour if pointage else Decimal(0)
            travailles += fraction
            a_payer = Decimal(0)
            if condition is None:
                if fraction:
                    raise ValidationError(
                        f"{ouvrier.nom_complet} : aucune condition de rémunération en vigueur le {jour:%d/%m/%Y}."
                    )
            elif condition.mode == ModeRemuneration.JOURNALIER:
                a_payer = condition.montant * fraction
            elif jour.weekday() in JOURS_OUVRABLES:
                if pointage is None:
                    non_pointes += 1
                    absence = Decimal(0)
                else:
                    absence = Decimal(0) if pointage.absence_justifiee else 1 - fraction
                absences += absence
                a_payer = condition.montant / jours_ouvrables_du_mois(jour) * (1 - absence)
            if a_payer and pointage is not None and pointage.ordre_fabrication_id:
                repartition = par_of.setdefault(pointage.ordre_fabrication_id, [Decimal(0), Decimal(0)])
                repartition[0] += fraction
                repartition[1] += a_payer
            total += a_payer
            jour += timedelta(days=1)
        self.jours_travailles, self.jours_absence_retenus, self.jours_non_pointes = travailles, absences, non_pointes
        self.montant = total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return par_of

    # -- règles ----------------------------------------------------------------
    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_code_unique(EtatPaie, "PAIE", champ="numero")
        super().save(*args, **kwargs)

    def clean(self):
        from apps.core.validation import verifier_transition
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutEtatPaie.PAYE, StatutEtatPaie.ANNULE):
            raise ValidationError(f"L'état de paie {self.numero} est {self.get_statut_display().lower()} : il ne change plus.")
        verifier_transition(ancien_statut, self.statut, self.TRANSITIONS, "statut de l'état de paie", initial=StatutEtatPaie.BROUILLON)
        if self.pk and any(valeur_en_base(self, c) != getattr(self, f"{c}_id" if c == "ouvrier" else c)
                           for c in ("ouvrier", "periodicite", "date_debut", "date_fin")):
            raise ValidationError("L'ouvrier et la période d'un état de paie ne changent pas : supprimez-le et préparez-en un autre.")
        if self.date_debut and self.date_fin and self.date_fin < self.date_debut:
            raise ValidationError({"date_fin": "La fin de période ne peut pas précéder son début."})
        if self.ouvrier_id and self.date_debut and self.date_fin and self.statut != StatutEtatPaie.ANNULE:
            autre = EtatPaie.objects.filter(
                ouvrier_id=self.ouvrier_id, date_debut__lte=self.date_fin, date_fin__gte=self.date_debut,
            ).exclude(pk=self.pk).exclude(statut=StatutEtatPaie.ANNULE).first()
            if autre:
                raise ValidationError(f"{self.ouvrier.nom_complet} a déjà un état de paie sur cette période : {autre.numero}.")

    def verifier_suppression(self):
        if self.statut != StatutEtatPaie.BROUILLON:
            raise ValidationError("Seul un état de paie préparé (non validé) peut être supprimé ; sinon, annulez-le.")

    # -- circuit ---------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def preparer(cls, periodicite, jour, utilisateur):
        """
        RH : prépare les états de la période contenant `jour` pour tous les
        ouvriers payés à cette périodicité, sous contrat sur la période et
        sans état déjà préparé. Retourne (états créés, erreurs par ouvrier).
        Un ouvrier sans rien à payer (journalier sans jour pointé) est ignoré.
        """
        debut, fin = periode_de_paie(periodicite, jour)
        crees, erreurs = [], {}
        ouvriers = Ouvrier.objects.filter(date_entree__lte=fin).filter(
            models.Q(date_fin_contrat__isnull=True) | models.Q(date_fin_contrat__gte=debut),
        ).exclude(etats_paie__in=cls.objects.filter(date_debut__lte=fin, date_fin__gte=debut).exclude(statut=StatutEtatPaie.ANNULE))
        for ouvrier in ouvriers.distinct():
            condition = ouvrier.condition_au(fin) or ouvrier.condition_au(debut)
            if condition is None or condition.periodicite_paie != periodicite:
                continue
            etat = cls(ouvrier=ouvrier, periodicite=periodicite, date_debut=debut, date_fin=fin, prepare_par=utilisateur)
            try:
                etat.calculer()
            except ValidationError as erreur:
                erreurs[ouvrier.matricule] = erreur.messages
                continue
            if etat.montant > 0:
                etat.save()
                crees.append(etat)
        return crees, erreurs

    def recalculer(self):
        if self.statut != StatutEtatPaie.BROUILLON:
            raise ValueError("Seul un état de paie préparé (non validé) peut être recalculé.")
        self.calculer()
        self.save()

    @transaction.atomic
    def valider(self, utilisateur):
        """
        DAF (ou Direction) : contrôle que les pointages n'ont pas changé
        depuis la préparation, constate la charge (D 661 / C 422) et
        impute aux OF le coût des jours pointés sur eux.
        """
        if self.statut != StatutEtatPaie.BROUILLON:
            raise ValueError(f"L'état de paie {self.numero} est déjà « {self.get_statut_display()} ».")
        if self.date_fin > timezone.localdate():
            raise ValueError(f"La période se termine le {self.date_fin:%d/%m/%Y} : elle ne peut pas encore être validée.")
        montant_prepare = self.montant
        par_of = self.calculer()
        if self.montant != montant_prepare:
            raise ValueError(
                f"Les pointages ont changé depuis la préparation ({montant_prepare} -> {self.montant}) : "
                "le RH doit recalculer l'état avant validation."
            )
        self.statut = StatutEtatPaie.VALIDE
        self.valide_par = utilisateur
        self.date_validation = timezone.now()
        self.save()
        from apps.comptabilite.ecritures import ecrire_etat_paie
        from apps.couts.models import CoutMainOeuvre
        ecrire_etat_paie(self)
        for of_id, (jours, montant) in par_of.items():
            heures = jours * HEURES_PAR_JOUR
            CoutMainOeuvre.objects.create(
                ordre_fabrication_id=of_id, heures=heures, etat_paie=self,
                cout_horaire=(montant / heures).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )

    @transaction.atomic
    def payer(self, caissier):
        """
        Caissier : remet les espèces à l'ouvrier. Crée le décaissement sur sa
        session ouverte, autorisé par la personne qui a validé la paie (la
        DAF), puis l'effectue (écriture D 422 / C 571, solde de caisse).
        """
        from apps.caisse.models import Decaissement, SessionCaisse, StatutSession
        if self.statut != StatutEtatPaie.VALIDE:
            raise ValueError(f"L'état de paie {self.numero} est « {self.get_statut_display()} » : seul un état validé se paie.")
        session = SessionCaisse.objects.filter(caissier=caissier, statut=StatutSession.OUVERTE).first()
        if session is None:
            raise ValueError("Ouvrez votre session de caisse pour payer.")
        ouvrier = self.ouvrier
        decaissement = Decaissement.objects.create(
            session_caisse=session, montant=self.montant, effectue_par=caissier,
            motif=f"Paie {self.numero} du {self.date_debut:%d/%m/%Y} au {self.date_fin:%d/%m/%Y}",
            beneficiaire=f"{ouvrier.matricule} {ouvrier.nom_complet}",
        )
        decaissement.autoriser(self.valide_par)
        self.decaissement = decaissement
        self.save(update_fields=["decaissement"])
        decaissement.effectuer(caissier)
        self.statut = StatutEtatPaie.PAYE
        self.date_paiement = timezone.now()
        self.save()

    @transaction.atomic
    def annuler(self, utilisateur, motif):
        """DAF : annule un état validé non payé (contre-passation, coûts des OF retirés)."""
        if self.statut != StatutEtatPaie.VALIDE:
            raise ValueError("Seul un état de paie validé et non payé peut être annulé (un état préparé se supprime).")
        if not (motif or "").strip():
            raise ValueError("Le motif d'annulation est obligatoire.")
        from apps.comptabilite.ecritures import ecrire_etat_paie
        self.statut = StatutEtatPaie.ANNULE
        self.motif_annulation = motif.strip()
        self.save()
        ecrire_etat_paie(self, annulation=True)
        self.couts_main_oeuvre.all().delete()

