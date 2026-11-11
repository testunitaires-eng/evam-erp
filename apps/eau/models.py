"""
Coût de l'eau traitée (site eau) - phase 1 : paramétrage.

Référence : classeur « EVAM_cout_standard_eau_TEST.xlsx » (onglets
Paramétrage, Règles de gestion, Rôles et droits). Ce module ne concerne
que le produit Eau ; Jus et Yaourt gardent la cascade de apps/couts.

Principe retenu (décisions du 2026-11-11) :
- les charges du forage (part du site eau) et du traitement forment le
  « coût de l'eau du mois » ; les OF sont valorisés au volume d'eau x le
  coût standard au m³ (phases suivantes) ;
- AUCUN effet rétroactif : un paramètre se modifie en créant une nouvelle
  version qui s'applique à partir d'un mois donné, jamais au mois en
  cours ni aux mois passés (règles 12 et 16 du classeur).

Contenu de la phase 1 :
- listes de valeurs : blocs, familles de charges, catégories, périodes
  (avec leur coefficient mensuel) ;
- ParametresEau : seuils et jour de clôture du site, versionnés ;
- CaracteristiquesEquipement : puissance (kW) et heures de marche
  standard par jour d'un équipement, versionnées.
"""

import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_pourcentage, exiger_positif_optionnel, valeur_en_base,
)

FORMAT_MOIS = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


# =====================================================================
# Mois (AAAA-MM)
# =====================================================================

def mois_de(jour):
    return jour.strftime("%Y-%m")


def mois_courant():
    return mois_de(timezone.localdate())


def mois_suivant(mois):
    annee, numero = (int(x) for x in mois.split("-"))
    return f"{annee + numero // 12:04d}-{numero % 12 + 1:02d}"


def verifier_format_mois(valeur, champ):
    if not FORMAT_MOIS.fullmatch(valeur or ""):
        raise ValidationError({champ: "Le mois doit être au format AAAA-MM (ex : 2026-12)."})


# =====================================================================
# Listes de valeurs (onglet Paramétrage, partie B)
# =====================================================================

class Bloc(models.TextChoices):
    """Les deux composantes du coût de l'eau."""
    FORAGE = "FORAGE", "Forage (commun aux deux sites)"
    TRAITEMENT = "TRAITEMENT", "Traitement de l'eau (site eau)"


class Famille(models.TextChoices):
    """Mode de calcul du coût mensuel prévisionnel d'une charge."""
    COURANTE = "COURANTE", "Courante"
    ETALEE = "ETALEE", "Étalée"
    PREVENTIVE = "PREVENTIVE", "Préventive"
    AU_BESOIN = "AU_BESOIN", "Au besoin"


FORMULES_FAMILLES = {
    Famille.COURANTE: (
        "Consommation régulière et prévisible.",
        "Quantité x prix x fréquence x coefficient de période x part site eau",
        "Factures et sorties de stock du mois",
    ),
    Famille.ETALEE: (
        "Bien qui sert plusieurs mois : son prix est réparti sur sa durée de vie.",
        "Quantité x prix ÷ durée de vie (mois) x part site eau",
        "Même calcul, à partir du mois d'installation ou de remplacement",
    ),
    Famille.PREVENTIVE: (
        "Entretien planifié à l'avance.",
        "Quantité x prix x fréquence x coefficient de période x part site eau",
        "Coût réel de l'intervention, en totalité, le mois où elle a lieu",
    ),
    Famille.AU_BESOIN: (
        "Charge imprévisible (panne, réparation).",
        "Aucune : non prévue dans le standard",
        "En totalité le mois où elle arrive ; étalée si grosse réparation qui prolonge la vie",
    ),
}


class Categorie(models.TextChoices):
    """Nature de la charge, pour les états et l'analyse des écarts."""
    ELECTRICITE = "ELECTRICITE", "Électricité"
    CARBURANT = "CARBURANT", "Carburant"
    AMORTISSEMENT = "AMORTISSEMENT", "Amortissement"
    DUREE_DE_VIE = "DUREE_DE_VIE", "Élément à durée de vie"
    CONSOMMABLE = "CONSOMMABLE", "Consommable"
    ANALYSE = "ANALYSE", "Analyse"
    MAINTENANCE_PREVENTIVE = "MAINTENANCE_PREVENTIVE", "Maintenance préventive"
    MAINTENANCE_AU_BESOIN = "MAINTENANCE_AU_BESOIN", "Maintenance au besoin"


class Periode(models.TextChoices):
    """Période d'une fréquence (« 3 fois par an », « 200 heures par mois »)."""
    JOUR = "JOUR", "Jour"
    SEMAINE = "SEMAINE", "Semaine"
    MOIS = "MOIS", "Mois"
    AN = "AN", "An"


# Coefficient mensuel = numérateur / dénominateur, gardé sous forme de
# fraction : on multiplie d'abord, on divise en dernier, pour retrouver
# exactement les montants du classeur (ex : 1 kit par semaine à 10 000
# = 10 000 x 52 / 12 = 43 333,33 et non 10 000 x 4,33).
COEFFICIENTS_PERIODES = {
    Periode.JOUR: (365, 12),
    Periode.SEMAINE: (52, 12),
    Periode.MOIS: (1, 1),
    Periode.AN: (1, 12),
}


def coefficient_mensuel(periode):
    numerateur, denominateur = COEFFICIENTS_PERIODES[periode]
    return Decimal(numerateur) / Decimal(denominateur)


def montant_mensuel_frequence(quantite, prix, frequence, periode):
    """Familles Courante et Préventive (avant part du site) : quantité x prix x fréquence ramenée au mois."""
    numerateur, denominateur = COEFFICIENTS_PERIODES[periode]
    return Decimal(quantite) * Decimal(prix) * Decimal(frequence) * numerateur / denominateur


def montant_mensuel_etale(quantite, prix, duree_vie_mois):
    """Famille Étalée (avant part du site) : quantité x prix ÷ durée de vie en mois."""
    return Decimal(quantite) * Decimal(prix) / Decimal(duree_vie_mois)


def bloc_de_l_etape(etape):
    """
    Forage si l'étape est le captage (ou l'une de ses sous-étapes) ;
    Traitement pour les autres étapes « amont » (traitement, cuves, UV,
    contrôle de l'eau) ; None hors coût de l'eau (ex : remplissage).
    """
    vues = set()
    courante = etape
    while courante is not None and courante.pk not in vues:
        if courante.code == "CAPTAGE":
            return Bloc.FORAGE
        vues.add(courante.pk)
        courante = courante.sous_etape_de
    if etape is not None and etape.phase == "AMONT":
        return Bloc.TRAITEMENT
    return None


def bloc_de_l_equipement(equipement):
    """Le bloc découle de l'étape du poste principal de l'équipement."""
    if equipement is None or not equipement.poste_id:
        return None
    return bloc_de_l_etape(equipement.poste.etape)


# =====================================================================
# Versions datées (aucun effet rétroactif)
# =====================================================================

class Versionnee(ValidationAvantEnregistrement, models.Model):
    """
    Paramètre versionné : chaque version s'applique à partir de son mois
    d'application (AAAA-MM) jusqu'à la version suivante. Pour une même
    clé (CLE = noms des champs qui identifient le paramètre) :
    - la première version (paramétrage initial) peut porter sur un mois
      passé et reste corrigeable tant qu'elle est la seule ;
    - toute nouvelle version s'applique au plus tôt le mois suivant ;
    - une version dont le mois a commencé est figée (ni modifiée ni
      supprimée) dès qu'une autre version existe : on en crée une
      nouvelle à la place.
    """
    CLE = ()

    mois_application = models.CharField("S'applique à partir du mois", max_length=7, help_text="AAAA-MM")
    motif = models.TextField("Motif de la modification", blank=True)
    saisi_par = models.ForeignKey(
        "comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    date_saisie = models.DateTimeField("Saisi le", auto_now_add=True)

    class Meta:
        abstract = True

    # -- clé et versions ---------------------------------------------------
    def _filtre_cle(self):
        attributs = (self._meta.get_field(champ).attname for champ in self.CLE)
        return {attribut: getattr(self, attribut) for attribut in attributs}

    def autres_versions(self):
        return type(self)._default_manager.filter(**self._filtre_cle()).exclude(pk=self.pk)

    @classmethod
    def en_vigueur(cls, mois, **cle):
        """Version qui s'applique au mois donné (None si aucune)."""
        return cls._default_manager.filter(mois_application__lte=mois, **cle).order_by("-mois_application").first()

    @property
    def figee(self):
        """Mois commencé et au moins une autre version : la version ne bouge plus."""
        if self.pk is None:
            return False
        mois = valeur_en_base(self, "mois_application") or self.mois_application
        return mois <= mois_courant() and self.autres_versions().exists()

    # -- règles ------------------------------------------------------------
    def clean_version(self):
        verifier_format_mois(self.mois_application, "mois_application")
        if self.figee:
            raise ValidationError(
                "Cette version s'applique déjà et ne peut plus être modifiée : "
                f"créez une nouvelle version à partir de {mois_suivant(mois_courant())}."
            )
        autres = self.autres_versions()
        if autres.filter(mois_application=self.mois_application).exists():
            raise ValidationError({"mois_application": f"Une version existe déjà pour {self.mois_application}."})
        if autres.exists() and self.mois_application <= mois_courant():
            raise ValidationError({"mois_application": (
                "Une modification ne s'applique qu'aux mois suivants : "
                f"choisissez {mois_suivant(mois_courant())} ou plus tard."
            )})

    def verifier_suppression(self):
        if self.figee:
            raise ValidationError("Cette version s'applique déjà : elle ne peut pas être supprimée.")


# =====================================================================
# Paramètres du site eau
# =====================================================================

class ParametresEau(Versionnee):
    """
    Seuils et règles du calcul du coût de l'eau pour un site (onglet
    Paramétrage : « Seuils », « Taux de rejet toléré », « Seuil de volume
    minimal », « Date de clôture du mois »).
    """
    CLE = ("usine",)

    usine = models.ForeignKey(
        "industriel.Usine", verbose_name="Site eau", on_delete=models.PROTECT, related_name="parametres_eau",
    )
    seuil_ecart_standard_pct = models.DecimalField(
        "Seuil d'écart du coût standard (%)", max_digits=5, decimal_places=2, default=Decimal("5"),
        help_text="Écart réel / standard (hors charges au besoin) au-delà duquel un nouveau standard est proposé.",
    )
    seuil_volume_minimal_pct = models.DecimalField(
        "Seuil de volume minimal (% du volume prévu)", max_digits=5, decimal_places=2, default=Decimal("50"),
        help_text="En dessous, le standard n'est pas révisé (le mois reste analysé).",
    )
    taux_rejet_tolere_pct = models.DecimalField(
        "Taux de rejet toléré (%)", max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Au-delà, l'eau des bouteilles rejetées est une perte anormale. Vide = à fixer.",
    )
    seuil_grosse_reparation = models.DecimalField(
        "Seuil de « grosse réparation » (FCFA HT)", max_digits=16, decimal_places=2, null=True, blank=True,
        help_text="Au-delà, une réparation qui prolonge la vie peut être étalée. Vide = à fixer avec l'expert-comptable.",
    )
    jour_cloture = models.PositiveSmallIntegerField(
        "Jour de clôture du mois", default=10,
        help_text="Jour du mois suivant jusqu'auquel on impute les charges du mois (ex : le 10).",
    )

    class Meta:
        verbose_name = "Paramètres du coût de l'eau"
        verbose_name_plural = "Paramètres du coût de l'eau"
        ordering = ["usine", "-mois_application"]
        constraints = [models.UniqueConstraint(fields=["usine", "mois_application"], name="parametres_eau_unique_par_mois")]

    def __str__(self):
        return f"Paramètres eau {self.usine.code} à partir de {self.mois_application}"

    def clean(self):
        self.clean_version()
        exiger_pourcentage(self.seuil_ecart_standard_pct, "seuil_ecart_standard_pct", "Le seuil d'écart")
        exiger_pourcentage(self.seuil_volume_minimal_pct, "seuil_volume_minimal_pct", "Le seuil de volume minimal")
        exiger_pourcentage(self.taux_rejet_tolere_pct, "taux_rejet_tolere_pct", "Le taux de rejet toléré")
        exiger_positif_optionnel(self.seuil_grosse_reparation, "seuil_grosse_reparation", "Le seuil de grosse réparation")
        if self.jour_cloture is None or not 1 <= self.jour_cloture <= 28:
            raise ValidationError({"jour_cloture": "Le jour de clôture doit être compris entre 1 et 28."})


# =====================================================================
# Caractéristiques des équipements
# =====================================================================

class CaracteristiquesEquipement(Versionnee):
    """
    Puissance et heures de marche standard d'un équipement (onglet
    Paramétrage : « Équipements », « Heures machine standard »). Les
    heures standard sont reportées chaque jour ; les techniciens ne
    saisissent que les exceptions (arrêts, pannes). Elles répartissent
    la facture d'électricité unique du site : part d'un équipement =
    kW x heures ÷ Σ (kW x heures). Concerne tous les équipements du
    site eau, y compris ceux de la ligne de production (leur part va au
    coût de la ligne, pas au coût de l'eau).
    """
    CLE = ("equipement",)

    equipement = models.ForeignKey(
        "industriel.Equipement", verbose_name="Équipement", on_delete=models.PROTECT, related_name="caracteristiques_eau",
    )
    puissance_kw = models.DecimalField("Puissance (kW)", max_digits=10, decimal_places=3, null=True, blank=True)
    heures_marche_jour = models.DecimalField(
        "Heures de marche standard par jour", max_digits=4, decimal_places=2, null=True, blank=True,
        help_text="Ex : pompe du forage 24 h/jour.",
    )

    class Meta:
        verbose_name = "Caractéristiques d'un équipement (eau)"
        verbose_name_plural = "Caractéristiques des équipements (eau)"
        ordering = ["equipement", "-mois_application"]
        constraints = [models.UniqueConstraint(
            fields=["equipement", "mois_application"], name="caracteristiques_equipement_unique_par_mois",
        )]

    def __str__(self):
        return f"{self.equipement.code} à partir de {self.mois_application}"

    @property
    def bloc(self):
        return bloc_de_l_equipement(self.equipement)

    def clean(self):
        self.clean_version()
        if self.puissance_kw is None and self.heures_marche_jour is None:
            raise ValidationError("Indiquez au moins la puissance ou les heures de marche standard.")
        exiger_positif_optionnel(self.puissance_kw, "puissance_kw", "La puissance", strict=True)
        exiger_positif_optionnel(self.heures_marche_jour, "heures_marche_jour", "Les heures de marche")
        if self.heures_marche_jour is not None and self.heures_marche_jour > 24:
            raise ValidationError({"heures_marche_jour": "Un équipement ne peut pas tourner plus de 24 h par jour."})
