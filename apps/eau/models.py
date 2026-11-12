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
    ValidationAvantEnregistrement, exiger_positif, exiger_pourcentage, exiger_positif_optionnel, valeur_en_base,
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


def ajouter_mois(mois, nombre):
    annee, numero = (int(x) for x in mois.split("-"))
    total = annee * 12 + numero - 1 + nombre
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def ecart_en_mois(debut, fin):
    """Nombre de mois de debut (inclus) à fin (exclu) : 2025-01 -> 2025-04 = 3."""
    a1, m1 = (int(x) for x in debut.split("-"))
    a2, m2 = (int(x) for x in fin.split("-"))
    return (a2 - a1) * 12 + m2 - m1


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

class JoursMarche(models.TextChoices):
    TOUS = "TOUS", "Tous les jours"
    LUNDI_SAMEDI = "LUNDI_SAMEDI", "Du lundi au samedi"
    LUNDI_VENDREDI = "LUNDI_VENDREDI", "Du lundi au vendredi"


# Jours de la semaine concernés (lundi = 0).
JOURS_DE_LA_SEMAINE = {
    JoursMarche.TOUS: frozenset(range(7)),
    JoursMarche.LUNDI_SAMEDI: frozenset(range(6)),
    JoursMarche.LUNDI_VENDREDI: frozenset(range(5)),
}


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
    jours_de_marche = models.CharField(
        "Jours de marche", max_length=15, choices=JoursMarche.choices, default=JoursMarche.TOUS,
        help_text="Jours où les heures standard sont reportées (ex : pompes du traitement selon le planning de production).",
    )
    pression_max_bar = models.DecimalField(
        "Pression maximale (bar)", max_digits=8, decimal_places=3, null=True, blank=True,
        help_text="Membranes : au-delà, alerte d'encrassement aux techniciens.",
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
        if self.puissance_kw is None and self.heures_marche_jour is None and self.pression_max_bar is None:
            raise ValidationError("Indiquez au moins la puissance, les heures de marche standard ou la pression maximale.")
        exiger_positif_optionnel(self.pression_max_bar, "pression_max_bar", "La pression maximale", strict=True)
        exiger_positif_optionnel(self.puissance_kw, "puissance_kw", "La puissance", strict=True)
        exiger_positif_optionnel(self.heures_marche_jour, "heures_marche_jour", "Les heures de marche")
        if self.heures_marche_jour is not None and self.heures_marche_jour > 24:
            raise ValidationError({"heures_marche_jour": "Un équipement ne peut pas tourner plus de 24 h par jour."})


# =====================================================================
# Phase 2 - Prévisionnel et coût standard (onglet « Calcul coût eau »)
# =====================================================================

class PrevisionVolume(Versionnee):
    """
    Bouteilles prévues par mois pour un format, en rythme normal (partie 1
    du calcul). Volume = bouteilles x contenance ÷ 1 000 (m³). Ce volume
    prévu sert aussi au seuil de volume minimal de la révision.
    Un format abandonné : nouvelle version à 0 bouteille.
    """
    CLE = ("usine", "article")

    usine = models.ForeignKey("industriel.Usine", verbose_name="Site eau", on_delete=models.PROTECT, related_name="+")
    article = models.ForeignKey(
        "referentiel.Article", verbose_name="Format (produit fini)", on_delete=models.PROTECT, related_name="previsions_eau",
    )
    bouteilles_par_mois = models.PositiveIntegerField("Bouteilles prévues par mois")

    class Meta:
        verbose_name = "Prévision de volume (format)"
        verbose_name_plural = "Prévisions de volume (formats)"
        ordering = ["usine", "article", "-mois_application"]
        constraints = [models.UniqueConstraint(fields=["usine", "article", "mois_application"], name="prevision_volume_unique_par_mois")]

    def __str__(self):
        return f"{self.article.code} : {self.bouteilles_par_mois} bouteilles/mois à partir de {self.mois_application}"

    @property
    def volume_m3(self):
        return Decimal(self.bouteilles_par_mois) * self.article.contenance / 1000

    def clean(self):
        self.clean_version()
        article = self.article if self.article_id else None
        if article is not None:
            if article.type_article != "PRODUIT_FINI":
                raise ValidationError({"article": "Choisissez un format de bouteille (produit fini)."})
            if not article.contenance or article.unite_contenance != "L":
                raise ValidationError({"article": f"La contenance en litres du format {article.code} n'est pas renseignée."})
            if self.usine_id and article.activite_id and self.usine.activites.exists() \
                    and not self.usine.activites.filter(pk=article.activite_id).exists():
                raise ValidationError({"article": f"Le format {article.code} n'est pas produit sur le site {self.usine.code}."})


class PrevisionCaptage(Versionnee):
    """
    Partage du forage prévu (débitmètres) : m³ captés par mois vers le site
    eau et vers les autres sites. Part du site eau = m³ site eau ÷ m³ total ;
    elle s'applique à toutes les charges du bloc Forage.
    """
    CLE = ("usine",)

    usine = models.ForeignKey("industriel.Usine", verbose_name="Site eau", on_delete=models.PROTECT, related_name="+")
    volume_site_eau_m3 = models.DecimalField("Eau captée vers le site eau (m³/mois)", max_digits=14, decimal_places=3)
    volume_autres_sites_m3 = models.DecimalField("Eau captée vers les autres sites (m³/mois)", max_digits=14, decimal_places=3)

    class Meta:
        verbose_name = "Prévision du partage du forage"
        verbose_name_plural = "Prévisions du partage du forage"
        ordering = ["usine", "-mois_application"]
        constraints = [models.UniqueConstraint(fields=["usine", "mois_application"], name="prevision_captage_unique_par_mois")]

    def __str__(self):
        return f"Captage prévu {self.usine.code} à partir de {self.mois_application}"

    @property
    def part_site_eau(self):
        total = self.volume_site_eau_m3 + self.volume_autres_sites_m3
        return self.volume_site_eau_m3 / total if total else Decimal(0)

    def clean(self):
        self.clean_version()
        exiger_positif(self.volume_site_eau_m3, "volume_site_eau_m3", "Le volume capté vers le site eau", strict=False)
        exiger_positif(self.volume_autres_sites_m3, "volume_autres_sites_m3", "Le volume capté vers les autres sites", strict=False)


class ElementCout(ValidationAvantEnregistrement, models.Model):
    """
    Un élément de coût de l'eau (une ligne de la partie 2 du calcul) :
    rattaché à une étape (donc à un bloc) et, si possible, à un
    équipement. Sa famille dit comment calculer son coût mensuel ; ses
    valeurs (quantité, prix, fréquence, durée de vie) sont dans ses
    versions (VersionElementCout), pour ne jamais toucher aux mois passés.
    """
    usine = models.ForeignKey("industriel.Usine", verbose_name="Site eau", on_delete=models.PROTECT, related_name="elements_cout_eau")
    libelle = models.CharField("Élément de coût", max_length=150)
    etape = models.ForeignKey("industriel.EtapeStandard", verbose_name="Étape", on_delete=models.PROTECT, related_name="+")
    equipement = models.ForeignKey(
        "industriel.Equipement", verbose_name="Équipement", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    famille = models.CharField("Famille", max_length=12, choices=Famille.choices)
    categorie = models.CharField("Catégorie", max_length=25, choices=Categorie.choices)
    unite = models.CharField("Unité de la quantité", max_length=20, blank=True, help_text="kW, kg, L, unité, lot, analyse, kit...")
    a_indiquer = models.CharField(
        "Ce qu'il faut indiquer", max_length=200, blank=True,
        help_text="Ex : puissance (kW) ; prix du kWh ; heures de marche par période.",
    )
    ordre = models.PositiveIntegerField("Ordre d'affichage", default=0)
    date_creation = models.DateTimeField("Créé le", auto_now_add=True)

    class Meta:
        verbose_name = "Élément de coût de l'eau"
        verbose_name_plural = "Éléments de coût de l'eau"
        ordering = ["usine", "ordre", "pk"]

    def __str__(self):
        return self.libelle

    @property
    def bloc(self):
        return bloc_de_l_etape(self.etape) if self.etape_id else None

    def clean(self):
        if not (self.libelle or "").strip():
            raise ValidationError({"libelle": "Le libellé est obligatoire."})
        if self.etape_id and self.bloc is None:
            raise ValidationError({"etape": "Choisissez une étape du forage ou du traitement de l'eau (hors coût de l'eau sinon)."})
        if self.equipement_id:
            if self.usine_id and self.equipement.usine_id != self.usine_id:
                raise ValidationError({"equipement": f"L'équipement {self.equipement.code} n'est pas sur ce site."})
            bloc_equipement = bloc_de_l_equipement(self.equipement)
            if bloc_equipement is not None and bloc_equipement != self.bloc:
                raise ValidationError({"equipement": f"L'équipement {self.equipement.code} est dans le bloc {bloc_equipement.label}, pas l'étape choisie."})
        ancienne = valeur_en_base(self, "famille")
        if ancienne and ancienne != self.famille:
            raise ValidationError({"famille": "La famille ne change pas (elle change le calcul des mois passés) : créez un nouvel élément."})

    def verifier_suppression(self):
        if self.versions.exists():
            raise ValidationError("Cet élément a des versions : retirez-le par une nouvelle version « retiré ».")


class VersionElementCout(Versionnee):
    """
    Valeurs d'un élément de coût à partir d'un mois. Champs attendus selon
    la famille :
    - Courante / Préventive : quantité, prix, fréquence, période ;
    - Étalée : quantité, prix, durée de vie (mois) ;
    - Au besoin : rien (jamais dans le prévisionnel).
    « Retiré » : l'élément ne compte plus à partir de ce mois.
    """
    CLE = ("element",)

    element = models.ForeignKey(ElementCout, verbose_name="Élément de coût", on_delete=models.PROTECT, related_name="versions")
    retire = models.BooleanField("Retiré à partir de ce mois", default=False)
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=4, null=True, blank=True)
    prix_unitaire = models.DecimalField("Prix unitaire HT (FCFA)", max_digits=16, decimal_places=4, null=True, blank=True)
    frequence = models.DecimalField("Fréquence (nombre par période)", max_digits=12, decimal_places=4, null=True, blank=True)
    periode = models.CharField("Période", max_length=10, choices=Periode.choices, blank=True)
    duree_vie_mois = models.PositiveIntegerField("Durée de vie (mois)", null=True, blank=True)

    class Meta:
        verbose_name = "Version d'un élément de coût"
        verbose_name_plural = "Versions des éléments de coût"
        ordering = ["element", "-mois_application"]
        constraints = [models.UniqueConstraint(fields=["element", "mois_application"], name="version_element_cout_unique_par_mois")]

    def __str__(self):
        return f"{self.element} à partir de {self.mois_application}"

    def montant_mensuel_avant_part(self):
        """Coût mensuel avant la part du site (0 si retiré ou famille « au besoin »)."""
        famille = self.element.famille
        if self.retire or famille == Famille.AU_BESOIN:
            return Decimal(0)
        if famille == Famille.ETALEE:
            return montant_mensuel_etale(self.quantite, self.prix_unitaire, self.duree_vie_mois)
        return montant_mensuel_frequence(self.quantite, self.prix_unitaire, self.frequence, self.periode)

    def clean(self):
        self.clean_version()
        if self.retire or not self.element_id:
            return
        famille = self.element.famille
        if famille == Famille.AU_BESOIN:
            if any(v not in (None, "") for v in (self.quantite, self.prix_unitaire, self.frequence, self.periode, self.duree_vie_mois)):
                raise ValidationError("Une charge « au besoin » n'est jamais prévue : aucune valeur à indiquer.")
            return
        exiger_positif(self.quantite, "quantite", "La quantité")
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire", strict=False)
        if famille == Famille.ETALEE:
            if not self.duree_vie_mois:
                raise ValidationError({"duree_vie_mois": "La durée de vie (en mois) est obligatoire pour une charge étalée."})
            if self.frequence is not None or self.periode:
                raise ValidationError({"frequence": "Une charge étalée n'a ni fréquence ni période."})
        else:
            exiger_positif(self.frequence, "frequence", "La fréquence")
            if not self.periode:
                raise ValidationError({"periode": "La période est obligatoire (jour, semaine, mois, an)."})
            if self.duree_vie_mois:
                raise ValidationError({"duree_vie_mois": "La durée de vie ne sert que pour une charge étalée."})


class StatutStandard(models.TextChoices):
    PROPOSE = "PROPOSE", "Proposé"
    VALIDE = "VALIDE", "Validé"
    REJETE = "REJETE", "Rejeté"


class OrigineStandard(models.TextChoices):
    PREVISIONNEL = "PREVISIONNEL", "Calcul prévisionnel"
    REVISION = "REVISION", "Révision mensuelle (coût réel)"


class CoutStandardEau(ValidationAvantEnregistrement, models.Model):
    """
    Coût standard de l'eau traitée au m³ d'un site, à partir d'un mois.
    Le logiciel propose, le contrôle de gestion valide : le standard ne
    change jamais automatiquement. Le calcul qui l'a produit est gardé
    (detail) : on sait toujours d'où vient chaque version.
    Le standard en vigueur pour un mois est le dernier validé dont le mois
    d'application est atteint ; il valorise l'eau des OF de ce mois.
    """
    usine = models.ForeignKey("industriel.Usine", verbose_name="Site eau", on_delete=models.PROTECT, related_name="couts_standards_eau")
    mois_application = models.CharField("S'applique à partir du mois", max_length=7, help_text="AAAA-MM")
    origine = models.CharField("Origine", max_length=15, choices=OrigineStandard.choices, default=OrigineStandard.PREVISIONNEL)
    statut = models.CharField("Statut", max_length=10, choices=StatutStandard.choices, default=StatutStandard.PROPOSE)
    volume_m3 = models.DecimalField("Volume d'eau du mois (m³)", max_digits=14, decimal_places=3)
    cout_forage = models.DecimalField("Coût du forage (part du site eau)", max_digits=16, decimal_places=2)
    cout_traitement = models.DecimalField("Coût du traitement", max_digits=16, decimal_places=2)
    cout_mensuel = models.DecimalField("Coût de l'eau du mois", max_digits=16, decimal_places=2)
    cout_m3 = models.DecimalField("Coût standard au m³ (FCFA)", max_digits=14, decimal_places=4)
    detail = models.JSONField("Détail du calcul", default=dict, blank=True)
    propose_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Proposé par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_proposition = models.DateTimeField("Proposé le", auto_now_add=True)
    valide_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Validé / rejeté par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_validation = models.DateTimeField("Validé / rejeté le", null=True, blank=True)
    motif = models.TextField("Motif", blank=True)

    class Meta:
        verbose_name = "Coût standard de l'eau"
        verbose_name_plural = "Coûts standards de l'eau"
        ordering = ["usine", "-mois_application", "-pk"]

    def __str__(self):
        return f"Standard eau {self.usine.code} {self.mois_application} : {self.cout_m3} FCFA/m³ ({self.get_statut_display()})"

    @property
    def cout_litre(self):
        return self.cout_m3 / 1000

    @classmethod
    def en_vigueur(cls, mois, **filtres):
        return cls.objects.filter(statut=StatutStandard.VALIDE, mois_application__lte=mois, **filtres) \
            .order_by("-mois_application", "-date_validation").first()

    def clean(self):
        verifier_format_mois(self.mois_application, "mois_application")
        ancien = valeur_en_base(self, "statut")
        if ancien and ancien != StatutStandard.PROPOSE:
            raise ValidationError("Un standard validé ou rejeté ne se modifie plus : proposez-en un nouveau.")
        exiger_positif(self.cout_m3, "cout_m3", "Le coût au m³", strict=False)

    def verifier_suppression(self):
        if self.statut != StatutStandard.PROPOSE:
            raise ValidationError("Un standard validé ou rejeté est historisé : il ne se supprime pas.")

    def _decider(self, utilisateur, statut, motif):
        if valeur_en_base(self, "statut") != StatutStandard.PROPOSE:
            raise ValueError("Seul un standard proposé peut être validé ou rejeté.")
        self.motif = motif or self.motif
        self.valide_par, self.date_validation = utilisateur, timezone.now()
        self.statut = statut
        self.save()

    def valider(self, utilisateur, motif=""):
        """
        Règle 14 : un standard validé s'applique à partir du 1er jour du
        mois suivant. Seul le tout premier standard du site (démarrage)
        peut porter sur le mois en cours ou un mois passé.
        """
        deja = CoutStandardEau.objects.filter(usine_id=self.usine_id, statut=StatutStandard.VALIDE).exclude(pk=self.pk)
        if deja.exists() and self.mois_application <= mois_courant():
            raise ValueError(
                "Un standard validé s'applique à partir du mois suivant : "
                f"proposez-le pour {mois_suivant(mois_courant())} ou plus tard."
            )
        if deja.filter(mois_application=self.mois_application).exists():
            raise ValueError(f"Un standard est déjà validé pour {self.mois_application}.")
        self._decider(utilisateur, StatutStandard.VALIDE, motif)

    def rejeter(self, utilisateur, motif):
        if not (motif or "").strip():
            raise ValueError("Le motif du rejet est obligatoire.")
        self._decider(utilisateur, StatutStandard.REJETE, motif)


# =====================================================================
# Phase 3 - Saisies du module « Traitement de l'eau » (techniciens)
# =====================================================================

def _pas_dans_le_futur(jour, champ="date"):
    if jour and jour > timezone.localdate():
        raise ValidationError({champ: "On ne saisit pas une date future."})


class TypeCompteur(models.TextChoices):
    COMPTEUR_FORAGE = "COMPTEUR_FORAGE", "Compteur du forage (eau captée au total)"
    DEBITMETRE = "DEBITMETRE", "Débitmètre forage -> site"


class Compteur(ValidationAvantEnregistrement, models.Model):
    """
    Instrument de mesure relevé chaque jour par les techniciens du site
    eau : le compteur du forage (eau captée au total) et un débitmètre
    par site desservi. Les débitmètres donnent la part de chaque site
    dans le forage ; le compteur du forage, le contrôle des pertes.
    """
    code = models.CharField("Code", max_length=30, unique=True)
    libelle = models.CharField("Libellé", max_length=100)
    type_compteur = models.CharField("Type", max_length=20, choices=TypeCompteur.choices)
    usine = models.ForeignKey(
        "industriel.Usine", verbose_name="Site qui le relève", on_delete=models.PROTECT, related_name="compteurs_eau",
    )
    site_desservi = models.ForeignKey(
        "industriel.Usine", verbose_name="Site desservi", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
        help_text="Débitmètre : le site vers lequel part l'eau mesurée.",
    )
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Compteur / débitmètre"
        verbose_name_plural = "Compteurs et débitmètres"
        ordering = ["usine", "type_compteur", "code"]

    def __str__(self):
        return f"{self.code} - {self.libelle}"

    def clean(self):
        if self.type_compteur == TypeCompteur.DEBITMETRE and not self.site_desservi_id:
            raise ValidationError({"site_desservi": "Indiquez le site desservi par ce débitmètre."})
        if self.type_compteur == TypeCompteur.COMPTEUR_FORAGE and self.site_desservi_id:
            raise ValidationError({"site_desservi": "Le compteur du forage mesure l'eau captée au total : pas de site desservi."})


class ReleveCompteur(ValidationAvantEnregistrement, models.Model):
    """Index d'un compteur un jour donné. Les index ne baissent jamais d'un relevé à l'autre."""
    compteur = models.ForeignKey(Compteur, verbose_name="Compteur", on_delete=models.PROTECT, related_name="releves")
    date = models.DateField("Date du relevé")
    index = models.DecimalField("Index (m³)", max_digits=14, decimal_places=3)
    observations = models.CharField("Observations", max_length=200, blank=True)
    saisi_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_saisie = models.DateTimeField("Saisi le", auto_now_add=True)

    class Meta:
        verbose_name = "Relevé de compteur"
        verbose_name_plural = "Relevés de compteurs"
        ordering = ["compteur", "-date"]
        constraints = [models.UniqueConstraint(fields=["compteur", "date"], name="releve_compteur_unique_par_jour")]

    def __str__(self):
        return f"{self.compteur.code} {self.date} : {self.index}"

    def clean(self):
        _pas_dans_le_futur(self.date)
        exiger_positif(self.index, "index", "L'index", strict=False)
        if not self.compteur_id or not self.date:
            return
        if not self.compteur.actif:
            raise ValidationError({"compteur": "Ce compteur n'est plus actif."})
        autres = ReleveCompteur.objects.filter(compteur_id=self.compteur_id).exclude(pk=self.pk)
        if autres.filter(date=self.date).exists():
            raise ValidationError({"date": f"Ce compteur est déjà relevé le {self.date:%d/%m/%Y} : corrigez ce relevé."})
        avant = autres.filter(date__lt=self.date).order_by("-date").first()
        apres = autres.filter(date__gt=self.date).order_by("date").first()
        if avant is not None and self.index < avant.index:
            raise ValidationError({"index": f"L'index ne peut pas baisser : {avant.index} relevé le {avant.date:%d/%m/%Y}."})
        if apres is not None and self.index > apres.index:
            raise ValidationError({"index": f"L'index dépasse celui relevé le {apres.date:%d/%m/%Y} ({apres.index})."})


class MotifArret(models.TextChoices):
    ARRET_PROGRAMME = "ARRET_PROGRAMME", "Arrêt programmé"
    PANNE = "PANNE", "Panne"
    LIGNE_ARRETEE = "LIGNE_ARRETEE", "Ligne à l'arrêt"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    COUPURE_COURANT = "COUPURE_COURANT", "Coupure de courant"
    AUTRE = "AUTRE", "Autre"


class ExceptionHeures(ValidationAvantEnregistrement, models.Model):
    """
    Heures de marche en moins un jour donné, pour un équipement ou pour
    une ligne entière (tous les équipements dont le poste est sur la
    ligne). Les heures standard sont reportées automatiquement chaque
    jour : seules les exceptions se saisissent (règle 8).
    """
    date = models.DateField("Date")
    equipement = models.ForeignKey(
        "industriel.Equipement", verbose_name="Équipement", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    ligne = models.ForeignKey(
        "industriel.Ligne", verbose_name="Ligne entière", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    heures_en_moins = models.DecimalField("Heures en moins", max_digits=4, decimal_places=2)
    motif = models.CharField("Motif", max_length=20, choices=MotifArret.choices)
    commentaire = models.CharField("Commentaire", max_length=200, blank=True)
    saisi_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_saisie = models.DateTimeField("Saisi le", auto_now_add=True)

    class Meta:
        verbose_name = "Exception d'heures machine"
        verbose_name_plural = "Exceptions d'heures machine"
        ordering = ["-date", "pk"]

    def __str__(self):
        cible = self.equipement.code if self.equipement_id else f"ligne {self.ligne.code}"
        return f"{cible} {self.date} : -{self.heures_en_moins} h"

    def clean(self):
        _pas_dans_le_futur(self.date)
        if bool(self.equipement_id) == bool(self.ligne_id):
            raise ValidationError("Indiquez soit un équipement, soit une ligne entière.")
        exiger_positif(self.heures_en_moins, "heures_en_moins", "Le nombre d'heures en moins")
        if self.heures_en_moins > 24:
            raise ValidationError({"heures_en_moins": "Une journée compte au plus 24 heures."})
        if self.motif == MotifArret.AUTRE and not (self.commentaire or "").strip():
            raise ValidationError({"commentaire": "Précisez le motif."})


class RelevePression(ValidationAvantEnregistrement, models.Model):
    """
    Relevé de pression (« DP ») d'une membrane. Au-delà de la pression
    maximale paramétrée pour l'équipement, les techniciens sont alertés
    immédiatement (encrassement).
    """
    equipement = models.ForeignKey("industriel.Equipement", verbose_name="Membrane / équipement", on_delete=models.PROTECT, related_name="+")
    date = models.DateField("Date")
    pression_bar = models.DecimalField("Pression (bar)", max_digits=8, decimal_places=3)
    observations = models.CharField("Observations", max_length=200, blank=True)
    saisi_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_saisie = models.DateTimeField("Saisi le", auto_now_add=True)

    class Meta:
        verbose_name = "Relevé de pression"
        verbose_name_plural = "Relevés de pression"
        ordering = ["-date", "equipement"]

    def __str__(self):
        return f"{self.equipement.code} {self.date} : {self.pression_bar} bar"

    @property
    def pression_max(self):
        if not self.equipement_id or not self.date:
            return None
        version = CaracteristiquesEquipement.en_vigueur(mois_de(self.date), equipement_id=self.equipement_id)
        return version.pression_max_bar if version else None

    @property
    def au_dessus_du_seuil(self):
        seuil = self.pression_max
        return seuil is not None and self.pression_bar > seuil

    def clean(self):
        _pas_dans_le_futur(self.date)
        exiger_positif(self.pression_bar, "pression_bar", "La pression", strict=False)

    def save(self, *args, **kwargs):
        creation = self._state.adding
        super().save(*args, **kwargs)
        if creation and self.au_dessus_du_seuil:
            from apps.comptes.models import Profil
            from apps.core.notifications import notifier
            notifier(
                f"Pression trop haute : {self.equipement.designation}",
                f"{self.pression_bar} bar le {self.date:%d/%m/%Y} (maximum {self.pression_max} bar) : encrassement probable.",
                document=self, profils=[Profil.TECHNICIEN_EAU],
            )


class TypePerte(models.TextChoices):
    NORMALE = "NORMALE", "Perte normale (absorbée dans le coût au m³)"
    ANORMALE = "ANORMALE", "Perte anormale (exclue du coût standard, suivie à part)"


class CausePerte(models.TextChoices):
    RINCAGE_BOUTEILLES = "RINCAGE_BOUTEILLES", "Rinçage des bouteilles"
    LAVAGE_FILTRES = "LAVAGE_FILTRES", "Lavage des filtres"
    CIP = "CIP", "Eau brute du CIP"
    REJET_ULTRAFILTRATION = "REJET_ULTRAFILTRATION", "Rejets de l'ultrafiltration"
    FUITE = "FUITE", "Fuite"
    DEBORDEMENT = "DEBORDEMENT", "Débordement"
    LOT_REJETE = "LOT_REJETE", "Lot rejeté"
    CASSE = "CASSE", "Casse"
    AUTRE = "AUTRE", "Autre"


# Onglet Paramétrage, « Types de pertes d'eau ».
TYPE_DE_LA_CAUSE = {
    CausePerte.RINCAGE_BOUTEILLES: TypePerte.NORMALE, CausePerte.LAVAGE_FILTRES: TypePerte.NORMALE,
    CausePerte.CIP: TypePerte.NORMALE, CausePerte.REJET_ULTRAFILTRATION: TypePerte.NORMALE,
    CausePerte.FUITE: TypePerte.ANORMALE, CausePerte.DEBORDEMENT: TypePerte.ANORMALE,
    CausePerte.LOT_REJETE: TypePerte.ANORMALE, CausePerte.CASSE: TypePerte.ANORMALE,
}


class PerteEau(ValidationAvantEnregistrement, models.Model):
    """
    Perte d'eau déclarée par les techniciens ou la production (règle 5) :
    un volume estimé, ou un nombre de bouteilles d'un format. Le type
    (normale / anormale) découle de la cause ; pour « Autre », on le choisit.
    Les pertes anormales seront valorisées au coût standard, hors standard.
    """
    usine = models.ForeignKey("industriel.Usine", verbose_name="Site eau", on_delete=models.PROTECT, related_name="+")
    date = models.DateField("Date")
    cause = models.CharField("Cause", max_length=25, choices=CausePerte.choices)
    type_perte = models.CharField("Type", max_length=10, choices=TypePerte.choices, blank=True)
    volume_estime_m3 = models.DecimalField("Volume estimé (m³)", max_digits=12, decimal_places=3, null=True, blank=True)
    article = models.ForeignKey(
        "referentiel.Article", verbose_name="Format des bouteilles", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
    )
    nombre_bouteilles = models.PositiveIntegerField("Nombre de bouteilles", null=True, blank=True)
    commentaire = models.CharField("Commentaire", max_length=200, blank=True)
    saisi_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_saisie = models.DateTimeField("Saisi le", auto_now_add=True)

    class Meta:
        verbose_name = "Perte d'eau"
        verbose_name_plural = "Pertes d'eau"
        ordering = ["-date", "pk"]

    def __str__(self):
        return f"{self.get_cause_display()} {self.date} : {self.volume_m3} m³"

    @property
    def volume_m3(self):
        if self.volume_estime_m3 is not None:
            return self.volume_estime_m3
        if self.article_id and self.nombre_bouteilles and self.article.contenance:
            return Decimal(self.nombre_bouteilles) * self.article.contenance / 1000
        return None

    def clean(self):
        _pas_dans_le_futur(self.date)
        if self.cause in TYPE_DE_LA_CAUSE:
            attendu = TYPE_DE_LA_CAUSE[self.cause]
            if self.type_perte and self.type_perte != attendu:
                raise ValidationError({"type_perte": f"« {CausePerte(self.cause).label} » est une {TypePerte(attendu).label.split(' (')[0].lower()}."})
            self.type_perte = attendu
        elif self.cause == CausePerte.AUTRE:
            if not self.type_perte:
                raise ValidationError({"type_perte": "Pour une cause « Autre », indiquez si la perte est normale ou anormale."})
            if not (self.commentaire or "").strip():
                raise ValidationError({"commentaire": "Précisez la cause."})
        par_volume = self.volume_estime_m3 is not None
        par_bouteilles = bool(self.article_id or self.nombre_bouteilles)
        if par_volume == par_bouteilles:
            raise ValidationError("Indiquez soit un volume estimé, soit un nombre de bouteilles avec leur format.")
        if par_volume:
            exiger_positif(self.volume_estime_m3, "volume_estime_m3", "Le volume estimé")
        else:
            if not (self.article_id and self.nombre_bouteilles):
                raise ValidationError({"nombre_bouteilles": "Indiquez le format et le nombre de bouteilles."})
            if not self.article.contenance or self.article.unite_contenance != "L":
                raise ValidationError({"article": f"La contenance en litres du format {self.article.code} n'est pas renseignée."})


# =====================================================================
# Phase 4 - Maintenance : interventions, pièces installées, alertes
# =====================================================================
#
# - Le plan de maintenance préventive, ce sont les éléments de coût de la
#   famille « Préventive » : l'opération, l'équipement et la fréquence
#   (nombre + période) y sont déjà, versionnés. On ne les saisit pas deux
#   fois ; l'échéance se calcule depuis la dernière intervention.
# - Les techniciens saisissent les interventions, sans montant : les
#   factures sont rattachées par la comptabilité (coût réel, phase 5).
# - Les pièces étalées réellement en place (membranes, lampes, sable,
#   équipements amortis) sont suivies lot par lot (Installation) : mois
#   d'installation, prix, durée de vie. Un remplacement avant la fin de
#   la durée de vie dégage la valeur résiduelle de l'ancien lot (règle 11).

def _quantite(valeur):
    return format(Decimal(valeur).normalize(), "f")


class TypeIntervention(models.TextChoices):
    PREVENTIVE = "PREVENTIVE", "Préventive (plan de maintenance)"
    AU_BESOIN = "AU_BESOIN", "Au besoin (panne, réparation)"
    REMPLACEMENT = "REMPLACEMENT", "Remplacement d'une pièce"


class Intervention(ValidationAvantEnregistrement, models.Model):
    """
    Intervention de maintenance sur un équipement du forage ou du
    traitement, saisie par les techniciens (sans montant).
    - Préventive : rattachée à une opération du plan (élément de coût
      « Préventive ») ; elle remet à zéro son échéance.
    - Au besoin : l'équipement réparé est obligatoire (règle 10).
    - Remplacement : la pièce remplacée (élément de coût « Étalée ») et la
      quantité ; le contrôle de gestion enregistre ensuite la nouvelle
      pièce (Installation) avec son prix.
    """
    equipement = models.ForeignKey("industriel.Equipement", verbose_name="Équipement", on_delete=models.PROTECT, related_name="+")
    type_intervention = models.CharField("Type", max_length=12, choices=TypeIntervention.choices)
    date = models.DateField("Date de l'intervention")
    description = models.TextField("Description")
    pieces_utilisees = models.TextField("Pièces et produits utilisés", blank=True)
    operation = models.ForeignKey(
        ElementCout, verbose_name="Opération du plan préventif", on_delete=models.PROTECT, null=True, blank=True,
        related_name="interventions", help_text="Intervention préventive : l'opération du plan réalisée.",
    )
    element_remplace = models.ForeignKey(
        ElementCout, verbose_name="Pièce remplacée", on_delete=models.PROTECT, null=True, blank=True,
        related_name="remplacements", help_text="Remplacement : l'élément étalé remplacé (membrane, lampe...).",
    )
    quantite_remplacee = models.DecimalField("Quantité remplacée", max_digits=14, decimal_places=4, null=True, blank=True)
    saisi_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_saisie = models.DateTimeField("Saisi le", auto_now_add=True)

    class Meta:
        verbose_name = "Intervention de maintenance"
        verbose_name_plural = "Interventions de maintenance"
        ordering = ["-date", "-pk"]

    def __str__(self):
        return f"{self.get_type_intervention_display()} - {self.equipement.code} le {self.date:%d/%m/%Y}"

    @property
    def usine(self):
        return self.equipement.usine if self.equipement_id else None

    def _verifier_element(self, element, champ, famille):
        if element.famille != famille:
            raise ValidationError({champ: f"« {element.libelle} » n'est pas un élément de la famille {Famille(famille).label}."})
        if element.usine_id != self.equipement.usine_id:
            raise ValidationError({champ: f"« {element.libelle} » n'est pas un élément du site de l'équipement."})
        if element.equipement_id and element.equipement_id != self.equipement_id:
            raise ValidationError({champ: f"« {element.libelle} » concerne l'équipement {element.equipement.code}."})

    def clean(self):
        _pas_dans_le_futur(self.date)
        if not (self.description or "").strip():
            raise ValidationError({"description": "Décrivez l'intervention."})
        if self.equipement_id and bloc_de_l_equipement(self.equipement) is None:
            raise ValidationError({"equipement": (
                f"{self.equipement.code} n'est pas un équipement du forage ou du traitement de l'eau "
                "(rattachez-le à un poste de ces étapes)."
            )})
        type_ = self.type_intervention
        if type_ == TypeIntervention.PREVENTIVE:
            if not self.operation_id:
                raise ValidationError({"operation": "Indiquez l'opération du plan de maintenance réalisée."})
            self._verifier_element(self.operation, "operation", Famille.PREVENTIVE)
        elif self.operation_id:
            raise ValidationError({"operation": "Seule une intervention préventive se rattache au plan."})
        if type_ == TypeIntervention.REMPLACEMENT:
            if not self.element_remplace_id:
                raise ValidationError({"element_remplace": "Indiquez la pièce remplacée."})
            self._verifier_element(self.element_remplace, "element_remplace", Famille.ETALEE)
            if self.quantite_remplacee is None:
                self.quantite_remplacee = Decimal(1)
            exiger_positif(self.quantite_remplacee, "quantite_remplacee", "La quantité remplacée")
        elif self.element_remplace_id or self.quantite_remplacee is not None:
            raise ValidationError({"element_remplace": "La pièce remplacée ne s'indique que pour un remplacement."})

    def verifier_suppression(self):
        if self.installations.exists():
            raise ValidationError("La nouvelle pièce de ce remplacement est déjà enregistrée : supprimez-la d'abord.")

    def save(self, *args, **kwargs):
        creation = self._state.adding
        super().save(*args, **kwargs)
        if creation and self.type_intervention in (TypeIntervention.AU_BESOIN, TypeIntervention.REMPLACEMENT):
            from apps.comptes.models import Profil
            from apps.core.notifications import notifier
            if self.type_intervention == TypeIntervention.AU_BESOIN:
                titre = f"Réparation : {self.equipement.designation}"
                message = f"Le {self.date:%d/%m/%Y} : {self.description} - facture à rattacher à l'équipement {self.equipement.code}."
            else:
                titre = f"Remplacement : {self.element_remplace.libelle}"
                message = (f"Le {self.date:%d/%m/%Y} sur {self.equipement.code} (quantité {_quantite(self.quantite_remplacee)}) : "
                           "enregistrer la nouvelle pièce et son prix ; valeur résiduelle de l'ancienne.")
            notifier(titre, message, document=self, profils=[Profil.CONTROLE_GESTION, Profil.COMPTABILITE_DAF])


class Installation(ValidationAvantEnregistrement, models.Model):
    """
    Un lot de pièces étalées réellement en place (élément de coût
    « Étalée ») : étalé sur sa durée de vie à partir de son mois
    d'installation. Un lot qui en remplace un autre (remplace = l'ancien
    lot) retire la quantité correspondante de l'ancien lot à partir de son
    mois ; la part de l'ancien prix pas encore étalée (valeur résiduelle)
    est imputée en totalité ce mois-là, comme charge exceptionnelle
    (règle 11). Ex : membrane de 1 000 000 sur 48 mois remplacée après
    12 mois : 1 000 000 x 36 ÷ 48 = 750 000.
    """
    element = models.ForeignKey(ElementCout, verbose_name="Élément étalé", on_delete=models.PROTECT, related_name="installations")
    quantite = models.DecimalField("Quantité", max_digits=14, decimal_places=4)
    prix_unitaire = models.DecimalField("Prix unitaire HT (FCFA)", max_digits=16, decimal_places=4)
    duree_vie_mois = models.PositiveIntegerField("Durée de vie (mois)")
    mois_installation = models.CharField("Mois d'installation", max_length=7, help_text="AAAA-MM : premier mois étalé.")
    remplace = models.ForeignKey(
        "self", verbose_name="Lot remplacé", on_delete=models.PROTECT, null=True, blank=True, related_name="remplacements",
    )
    intervention = models.ForeignKey(
        Intervention, verbose_name="Intervention de remplacement", on_delete=models.PROTECT, null=True, blank=True,
        related_name="installations",
    )
    observations = models.CharField("Observations", max_length=200, blank=True)
    saisi_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_saisie = models.DateTimeField("Saisi le", auto_now_add=True)

    class Meta:
        verbose_name = "Pièce installée (lot étalé)"
        verbose_name_plural = "Pièces installées (lots étalés)"
        ordering = ["element", "-mois_installation", "-pk"]

    def __str__(self):
        return f"{self.element} x {_quantite(self.quantite)} installé(e) en {self.mois_installation}"

    @property
    def dernier_mois(self):
        """Dernier mois étalé (fin de vie)."""
        return ajouter_mois(self.mois_installation, self.duree_vie_mois - 1)

    def quantite_remplacee(self, mois, sauf=None):
        """Quantité de ce lot remplacée par des lots installés au plus tard ce mois-là."""
        lots = self.remplacements.filter(mois_installation__lte=mois)
        if sauf is not None and sauf.pk:
            lots = lots.exclude(pk=sauf.pk)
        return sum((lot.quantite for lot in lots), Decimal(0))

    def quantite_en_place(self, mois):
        if mois < self.mois_installation:
            return Decimal(0)
        return self.quantite - self.quantite_remplacee(mois)

    def montant_etale(self, mois):
        """Étalement du mois (exact) : prix x quantité en place ÷ durée de vie, pendant la durée de vie."""
        if not (self.mois_installation <= mois <= self.dernier_mois):
            return Decimal(0)
        return montant_mensuel_etale(self.quantite_en_place(mois), self.prix_unitaire, self.duree_vie_mois)

    @property
    def mois_deja_etales(self):
        """Pour un lot de remplacement : mois de l'ancien lot étalés avant le remplacement."""
        if not self.remplace_id:
            return None
        return min(ecart_en_mois(self.remplace.mois_installation, self.mois_installation), self.remplace.duree_vie_mois)

    @property
    def valeur_residuelle(self):
        """Charge exceptionnelle du mois d'installation (exacte) : part de l'ancien prix pas encore étalée."""
        if not self.remplace_id:
            return None
        ancien = self.remplace
        reste = ancien.duree_vie_mois - self.mois_deja_etales
        return Decimal(ancien.prix_unitaire) * Decimal(self.quantite) * reste / ancien.duree_vie_mois

    def clean(self):
        verifier_format_mois(self.mois_installation, "mois_installation")
        exiger_positif(self.quantite, "quantite", "La quantité")
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire", strict=False)
        if not self.duree_vie_mois:
            raise ValidationError({"duree_vie_mois": "La durée de vie (en mois) est obligatoire."})
        if self.element_id and self.element.famille != Famille.ETALEE:
            raise ValidationError({"element": "Seul un élément de la famille « Étalée » s'installe par lots."})
        if self.remplace_id:
            ancien = self.remplace
            if ancien.pk == self.pk:
                raise ValidationError({"remplace": "Un lot ne se remplace pas lui-même."})
            if ancien.element_id != self.element_id:
                raise ValidationError({"remplace": "Le lot remplacé n'est pas le même élément."})
            if self.mois_installation <= ancien.mois_installation:
                raise ValidationError({"mois_installation": f"Le lot remplacé a été installé en {ancien.mois_installation} : le remplacement vient après."})
            disponible = ancien.quantite - ancien.quantite_remplacee(self.mois_installation, sauf=self)
            if self.quantite > disponible:
                raise ValidationError({"quantite": f"Il ne reste que {_quantite(disponible)} en place dans le lot remplacé."})
        if self.intervention_id:
            intervention = self.intervention
            if intervention.type_intervention != TypeIntervention.REMPLACEMENT or intervention.element_remplace_id != self.element_id:
                raise ValidationError({"intervention": "Choisissez l'intervention de remplacement de cette pièce."})
            if mois_de(intervention.date) != self.mois_installation:
                raise ValidationError({"mois_installation": f"Le remplacement a eu lieu en {mois_de(intervention.date)}."})
            if not self.remplace_id:
                raise ValidationError({"remplace": "Indiquez le lot remplacé (pour sa valeur résiduelle)."})
        if self.pk and self.remplacements.exists():
            for champ in ("element_id", "quantite", "prix_unitaire", "duree_vie_mois", "mois_installation"):
                if getattr(self, champ) != valeur_en_base(self, champ):
                    raise ValidationError("Ce lot a déjà été (en partie) remplacé : ses valeurs ne changent plus.")

    def verifier_suppression(self):
        if self.remplacements.exists():
            raise ValidationError("Ce lot a déjà été (en partie) remplacé : il ne peut pas être supprimé.")


class AlerteEnvoyee(models.Model):
    """Trace des alertes datées déjà envoyées (préventive à faire, fin de vie) : chacune n'est envoyée qu'une fois."""
    cle = models.CharField("Clé", max_length=120, unique=True)
    date = models.DateTimeField("Envoyée le", auto_now_add=True)

    class Meta:
        verbose_name = "Alerte de maintenance envoyée"
        verbose_name_plural = "Alertes de maintenance envoyées"

    def __str__(self):
        return self.cle
