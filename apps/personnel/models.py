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

Phases suivantes (non couvertes ici) : conditions de rémunération,
pointages, états de paie, écritures comptables, coût par OF.
"""

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

    def verifier_suppression(self):
        if self.affectations.exists():
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
