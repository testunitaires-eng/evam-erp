"""
Module 10 - Coûts et Rentabilité.

Calcule le coût réel de production à partir de 4 sources (§13.2-13.10) :
matières consommées, énergie (eau/électricité), main-d'œuvre et
amortissements. Compare au coût standard pour dégager les écarts et la
marge.

ATTENTION - voir README.md section "Limites connues" : les règles
exactes de calcul (clés de répartition, formules de marge) doivent
être validées avec le client (DAF) avant mise en production. Les
modèles ci-dessous posent la structure de données ; le calcul détaillé
(CoutReel.calculer()) est un point à finaliser avec le client.
"""

import re

from django.core.exceptions import ValidationError
from django.db import models
from apps.referentiel.models import Article
from apps.production.models import OrdreFabrication
from apps.core.validation import ValidationAvantEnregistrement, exiger_positif


class CoutMatiere(ValidationAvantEnregistrement, models.Model):
    """Valorisation d'une sortie matière (quantité x coût unitaire de la matière)."""
    article = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    cout_unitaire = models.DecimalField("Coût unitaire", max_digits=14, decimal_places=4)
    date_valorisation = models.DateField("Date de valorisation")

    class Meta:
        verbose_name = "Coût matière"
        verbose_name_plural = "Coûts matières"

    def __str__(self):
        return f"{self.article.code} : {self.cout_unitaire}"

    def clean(self):
        exiger_positif(self.cout_unitaire, "cout_unitaire", "Le coût unitaire", strict=False)


class TypeEnergie(models.TextChoices):
    ELECTRICITE = "ELECTRICITE", "Électricité"
    EAU_CAPTAGE = "EAU_CAPTAGE", "Eau / captage-forage"


class CoutEnergie(ValidationAvantEnregistrement, models.Model):
    """Charge d'énergie sur une période, à répartir sur les OF de la période (clé de répartition à définir avec le client)."""
    type_energie = models.CharField("Type d'énergie", max_length=20, choices=TypeEnergie.choices)
    periode = models.CharField("Période", max_length=20, help_text="Format AAAA-MM")
    montant = models.DecimalField("Montant de la charge", max_digits=14, decimal_places=2)
    cle_repartition = models.CharField(
        "Clé de répartition", max_length=100, blank=True,
        help_text="Ex : au prorata des quantités produites, ou des heures machine.",
    )

    class Meta:
        verbose_name = "Coût d'énergie"
        verbose_name_plural = "Coûts d'énergie"

    def __str__(self):
        return f"{self.get_type_energie_display()} {self.periode} : {self.montant}"

    def clean(self):
        exiger_positif(self.montant, "montant", "Le montant de la charge", strict=False)
        # La période sert de clé de rapprochement avec les OF (CoutReel.calculer) :
        # un format différent rendrait la charge invisible dans les calculs.
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", self.periode or ""):
            raise ValidationError({"periode": "La période doit être au format AAAA-MM (ex : 2026-09)."})


class CoutMainOeuvre(ValidationAvantEnregistrement, models.Model):
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.CASCADE, related_name="couts_main_oeuvre",
    )
    heures = models.DecimalField("Heures travaillées", max_digits=8, decimal_places=2)
    cout_horaire = models.DecimalField("Coût horaire", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Coût main-d'œuvre"
        verbose_name_plural = "Coûts main-d'œuvre"

    def __str__(self):
        return f"{self.ordre_fabrication.numero} : {self.heures}h x {self.cout_horaire}"

    def clean(self):
        exiger_positif(self.heures, "heures", "Le nombre d'heures")
        exiger_positif(self.cout_horaire, "cout_horaire", "Le coût horaire", strict=False)

    @property
    def cout_total(self):
        return self.heures * self.cout_horaire


class Amortissement(ValidationAvantEnregistrement, models.Model):
    immobilisation = models.CharField("Immobilisation", max_length=200)
    valeur = models.DecimalField("Valeur d'origine", max_digits=14, decimal_places=2)
    duree_amortissement_mois = models.PositiveIntegerField("Durée d'amortissement (mois)")
    date_debut = models.DateField("Date de début d'amortissement")

    class Meta:
        verbose_name = "Amortissement"
        verbose_name_plural = "Amortissements"

    def __str__(self):
        return self.immobilisation

    def clean(self):
        exiger_positif(self.valeur, "valeur", "La valeur d'origine")
        exiger_positif(self.duree_amortissement_mois, "duree_amortissement_mois", "La durée d'amortissement")

    @property
    def amortissement_mensuel(self):
        if self.duree_amortissement_mois:
            return self.valeur / self.duree_amortissement_mois
        return 0


class CoutStandard(ValidationAvantEnregistrement, models.Model):
    """Coût standard de référence d'un article, comparé au coût réel constaté (§13.9)."""
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.CASCADE, related_name="couts_standards")
    cout_standard_unitaire = models.DecimalField("Coût standard unitaire", max_digits=14, decimal_places=4)
    date_debut_validite = models.DateField("Valide à partir du")

    class Meta:
        verbose_name = "Coût standard"
        verbose_name_plural = "Coûts standards"

    def __str__(self):
        return f"Standard {self.article.code} : {self.cout_standard_unitaire}"

    def clean(self):
        exiger_positif(self.cout_standard_unitaire, "cout_standard_unitaire", "Le coût standard unitaire", strict=False)


class CoutReel(models.Model):
    """
    Coût réel constaté d'un OF, agrégé à partir des matières, de la
    main-d'œuvre, de l'énergie et des amortissements imputés.

    NOTE IMPORTANTE : les champs ci-dessous sont pré-calculés et
    stockés (plutôt que recalculés à la volée) pour conserver un
    historique figé même si les coûts unitaires changent ensuite.
    La méthode de calcul détaillée est à construire avec le client
    (voir README.md).
    """
    ordre_fabrication = models.OneToOneField(
        OrdreFabrication, verbose_name="Ordre de fabrication",
        on_delete=models.CASCADE, related_name="cout_reel",
    )
    cout_matiere_total = models.DecimalField("Coût matières total", max_digits=16, decimal_places=2, default=0)
    cout_main_oeuvre_total = models.DecimalField("Coût main-d'œuvre total", max_digits=16, decimal_places=2, default=0)
    cout_energie_total = models.DecimalField("Coût énergie total", max_digits=16, decimal_places=2, default=0)
    cout_amortissement_total = models.DecimalField("Coût amortissement total", max_digits=16, decimal_places=2, default=0)
    cout_charges_reparties = models.DecimalField(
        "Charges imputées (cascade)", max_digits=16, decimal_places=2, default=0,
        help_text="Charges de production rattachées à une étape puis réparties par inducteur jusqu'à cet OF.",
    )
    date_calcul = models.DateTimeField("Date de calcul", auto_now=True)

    class Meta:
        verbose_name = "Coût réel"
        verbose_name_plural = "Coûts réels"

    def __str__(self):
        return f"Coût réel {self.ordre_fabrication.numero} : {self.cout_total}"

    @property
    def cout_total(self):
        return (
            self.cout_matiere_total + self.cout_main_oeuvre_total
            + self.cout_energie_total + self.cout_amortissement_total + self.cout_charges_reparties
        )

    @property
    def quantite_produite(self):
        """
        Quantité réellement produite et bonne : somme des lots de l'OF
        (hors lots non conformes, qui sont une perte). À défaut de lot,
        la quantité prévue.
        """
        return self.ordre_fabrication.quantite_produite_bonne

    @property
    def prix_vente_moyen(self):
        """Prix de vente HT moyen de l'article facturé (factures non annulées), ou None."""
        from django.db.models import Sum
        from apps.commercial.models import LigneFacture
        totaux = LigneFacture.objects.filter(
            article=self.ordre_fabrication.article,
        ).exclude(facture__statut="ANNULEE").aggregate(ht=Sum("montant_ht"), quantite=Sum("quantite"))
        if not totaux["quantite"]:
            return None
        return totaux["ht"] / totaux["quantite"]

    @property
    def marge_unitaire(self):
        prix = self.prix_vente_moyen
        return None if prix is None else prix - self.cout_unitaire_reel

    @property
    def taux_marge(self):
        prix = self.prix_vente_moyen
        return None if not prix else round(self.marge_unitaire / prix * 100, 2)

    @property
    def cout_unitaire_reel(self):
        quantite = self.quantite_produite
        return self.cout_total / quantite if quantite else 0

    @property
    def ecart_vs_standard(self):
        """Différence coût réel - coût standard. Positif = surcoût."""
        standard = (
            self.ordre_fabrication.article.couts_standards
            .order_by("-date_debut_validite").first()
        )
        if not standard:
            return None
        return self.cout_unitaire_reel - standard.cout_standard_unitaire

    def calculer(self):
        """
        Recalcule et enregistre les 4 composantes du coût réel de l'OF
        (§13.2-13.8 du cahier des charges) :

        1. Matières : somme des sorties matières de l'OF, valorisées au
           dernier coût unitaire connu de chaque matière (CoutMatiere).
           Les retours matières sont déduits (consommation nette, §8.8).
        2. Main-d'œuvre : somme des CoutMainOeuvre liés à l'OF.
        3. Énergie : quote-part des charges d'énergie de la période de
           l'OF, répartie au prorata de la quantité produite par cet OF
           par rapport à la quantité totale produite ce mois-là (clé de
           répartition par défaut - à ajuster avec le client si une
           autre clé est retenue, ex. heures machine).
        4. Amortissement : quote-part mensuelle des amortissements en
           cours, répartie selon la même clé que l'énergie.

        Cette méthode est volontairement explicite et commentée car les
        clés de répartition exactes sont un point à valider avec le
        DAF (voir README.md, section Limites connues).
        """
        from apps.production.models import SortieMatiere, RetourMatiere, OrdreFabrication
        from django.db.models import Sum

        of = self.ordre_fabrication

        # 1. Coût matières = valeur RÉELLE des sorties matières de l'OF
        #    (au CMUP du jour de la sortie) - valeur des retours magasin.
        #    Mouvements anciens sans valeur : dernier coût matière connu.
        from apps.stocks.models import MouvementStock
        cout_matieres = 0
        # Les fluides de process (eau traitée) ne s'achètent pas : leur coût est
        # celui du captage, du traitement et du stockage process, imputé par la
        # cascade au volume d'eau (pas de double compte).
        for mouvement in MouvementStock.objects.filter(
            document_origine=of.numero, type_mouvement__in=["SORTIE", "RETOUR"],
        ).exclude(article__type_article="FLUIDE_PROCESS"):
            valeur = mouvement.valeur
            if valeur is None:
                dernier = CoutMatiere.objects.filter(article_id=mouvement.article_id).order_by("-date_valorisation").first()
                valeur = mouvement.quantite * dernier.cout_unitaire if dernier else 0
            cout_matieres += valeur if mouvement.type_mouvement == "SORTIE" else -valeur

        # 2. Coût main-d'œuvre = somme des lignes liées à l'OF
        cout_main_oeuvre = sum(
            (ligne.cout_total for ligne in self.ordre_fabrication.couts_main_oeuvre.all()),
            start=0,
        )

        # 3 & 4. Énergie et amortissement : répartis au prorata de la
        # quantité produite par cet OF vs la quantité totale du mois.
        periode = of.date_creation.strftime("%Y-%m") if of.date_creation else None
        cout_energie = 0
        cout_amortissement = 0
        # Charges de la cascade (par étape et inducteur) déjà réparties sur l'OF.
        cout_charges = RepartitionCout.objects.filter(
            ordre_fabrication=of, niveau=NiveauRepartition.PRODUIT,
            charge__nature__categorie=CategorieCout.PRODUCTION,
        ).aggregate(total=Sum("montant"))["total"] or 0
        # Ancienne répartition au prorata des quantités (clé arbitraire) : seulement
        # tant qu'aucune charge n'est saisie dans la cascade pour la période.
        periodes = {periode} | ({of.date_fin.strftime("%Y-%m")} if of.date_fin else set())
        if periode and Charge.objects.filter(periode__in=periodes).exists():
            periode = None
        if periode:
            quantite_totale_periode = OrdreFabrication.objects.filter(
                date_creation__year=of.date_creation.year,
                date_creation__month=of.date_creation.month,
            ).aggregate(total=Sum("quantite_a_produire"))["total"] or 0

            if quantite_totale_periode:
                part_of = of.quantite_a_produire / quantite_totale_periode

                charges_energie = CoutEnergie.objects.filter(periode=periode).aggregate(
                    total=Sum("montant")
                )["total"] or 0
                cout_energie = charges_energie * part_of

                amortissements_en_cours = Amortissement.objects.filter(
                    date_debut__lte=of.date_creation
                )
                total_amortissement_mensuel = sum(
                    (a.amortissement_mensuel for a in amortissements_en_cours), start=0
                )
                cout_amortissement = total_amortissement_mensuel * part_of

        self.cout_matiere_total = cout_matieres
        self.cout_main_oeuvre_total = cout_main_oeuvre
        self.cout_energie_total = cout_energie
        self.cout_amortissement_total = cout_amortissement
        self.cout_charges_reparties = cout_charges
        self.save()
        return self


# =====================================================================
# Coûts en cascade (documents « Modèle de calcul des coûts » Eau / Jus /
# Yaourt et « Clés d'imputation et de répartition ») :
#     charge -> étape -> direct / indirect -> activité -> OF
#            -> produit / format -> pack -> unité
# - une charge est rattachée à l'étape où elle est consommée ;
# - commune, elle est répartie avec l'inducteur qui explique sa
#   consommation (m³ d'eau, bouteilles, packs, heures machine...) ;
# - jamais de clé arbitraire : sans valeur d'inducteur, la charge reste
#   NON RÉPARTIE ;
# - les répartitions successives ventilent la même charge (somme des
#   parts = montant du niveau supérieur, contrôlé) ;
# - stockage produit fini et distribution sont calculés à part.
# =====================================================================

class Inducteur(models.TextChoices):
    VOLUME_EAU_M3 = "VOLUME_EAU_M3", "Volume d'eau (m³)"
    BOUTEILLES = "BOUTEILLES", "Nombre de bouteilles / pots produits"
    PACKS = "PACKS", "Nombre de packs / cartons"
    PALETTES = "PALETTES", "Nombre de palettes"
    LITRES_PRODUITS = "LITRES_PRODUITS", "Litres produits"
    HEURES_MACHINE = "HEURES_MACHINE", "Heures machine"
    HEURES_MO = "HEURES_MO", "Heures de main-d'œuvre"
    KWH = "KWH", "kWh"
    ANALYSES_PONDEREES = "ANALYSES_PONDEREES", "Analyses pondérées"
    PALETTES_JOURS = "PALETTES_JOURS", "Palettes-jours (stockage)"
    KM = "KM", "Kilomètres (tournées)"
    QUANTITE_LIVREE = "QUANTITE_LIVREE", "Quantité livrée"
    AUCUN = "AUCUN", "Aucun (charge directe uniquement)"


UNITES_INDUCTEURS = {
    Inducteur.VOLUME_EAU_M3: "m³", Inducteur.BOUTEILLES: "unités", Inducteur.PACKS: "packs",
    Inducteur.PALETTES: "palettes", Inducteur.LITRES_PRODUITS: "L", Inducteur.HEURES_MACHINE: "h",
    Inducteur.HEURES_MO: "h", Inducteur.KWH: "kWh", Inducteur.ANALYSES_PONDEREES: "analyses pondérées",
    Inducteur.PALETTES_JOURS: "palettes-jours", Inducteur.KM: "km", Inducteur.QUANTITE_LIVREE: "unités livrées",
    Inducteur.AUCUN: "",
}


class CategorieCout(models.TextChoices):
    PRODUCTION = "PRODUCTION", "Coût de production"
    STOCKAGE = "STOCKAGE", "Stockage produit fini (hors production)"
    DISTRIBUTION = "DISTRIBUTION", "Distribution (hors production)"
    HORS_COUT = "HORS_COUT", "Frais généraux non incorporés"


class Traitement(models.TextChoices):
    DIRECT = "DIRECT", "Direct (identifiable sans clé)"
    INDIRECT = "INDIRECT", "Indirect (commun, réparti par clé)"


class CategorieEconomique(models.TextChoices):
    ENERGIE = "ENERGIE", "Énergie"
    MAINTENANCE = "MAINTENANCE", "Maintenance"
    PIECES = "PIECES", "Pièces de rechange / lubrifiants"
    MAIN_OEUVRE = "MAIN_OEUVRE", "Main-d'œuvre"
    AMORTISSEMENT = "AMORTISSEMENT", "Amortissement"
    PRODUITS_TRAITEMENT = "PRODUITS_TRAITEMENT", "Produits de traitement / nettoyage / filtres"
    ANALYSES = "ANALYSES", "Analyses / laboratoire"
    EMBALLAGES = "EMBALLAGES", "Emballages / consommables"
    LOCATION = "LOCATION", "Bâtiment / location"
    CARBURANT = "CARBURANT", "Carburant / péages"
    SOUS_TRAITANCE = "SOUS_TRAITANCE", "Sous-traitance"
    AUTRE = "AUTRE", "Autre"


class NatureCout(ValidationAvantEnregistrement, models.Model):
    """Paramétrage d'un élément de coût (Guide §15) : étape, direct/indirect, inducteur, justification de la clé."""
    code = models.CharField("Code", max_length=30, unique=True, editable=False)
    libelle = models.CharField("Élément de coût", max_length=150)
    etape = models.ForeignKey(
        "industriel.EtapeStandard", verbose_name="Étape", on_delete=models.PROTECT, null=True, blank=True,
        related_name="natures_cout",
    )
    categorie = models.CharField("Catégorie", max_length=15, choices=CategorieCout.choices, default=CategorieCout.PRODUCTION)
    categorie_economique = models.CharField("Catégorie économique", max_length=20, choices=CategorieEconomique.choices, default=CategorieEconomique.AUTRE)
    traitement = models.CharField("Traitement", max_length=10, choices=Traitement.choices, default=Traitement.INDIRECT)
    inducteur = models.CharField("Clé / inducteur", max_length=20, choices=Inducteur.choices)
    justification = models.TextField("Justification de la clé", blank=True)
    date_debut = models.DateField("Valide à partir du", null=True, blank=True)
    date_fin = models.DateField("Valide jusqu'au", null=True, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Nature de coût (paramétrage)"
        verbose_name_plural = "Natures de coût (paramétrage)"
        ordering = ["categorie", "etape__ordre_reference", "libelle"]

    def __str__(self):
        etape = f" [{self.etape.libelle}]" if self.etape_id else ""
        return f"{self.libelle}{etape}"

    def save(self, *args, **kwargs):
        if not self.code:
            from apps.core.models import generer_code_unique
            self.code = generer_code_unique(NatureCout, "NAT", largeur=3)
        super().save(*args, **kwargs)

    def clean(self):
        if not (self.libelle or "").strip():
            raise ValidationError({"libelle": "Le libellé est obligatoire."})
        if self.traitement == Traitement.INDIRECT and self.inducteur == Inducteur.AUCUN \
                and self.categorie != CategorieCout.HORS_COUT:
            raise ValidationError({"inducteur": "Une charge indirecte se répartit avec un inducteur (pas de clé arbitraire)."})
        if self.categorie == CategorieCout.PRODUCTION and self.inducteur in (Inducteur.PALETTES_JOURS, Inducteur.KM, Inducteur.QUANTITE_LIVREE):
            raise ValidationError({"inducteur": "Cet inducteur sert au stockage ou à la distribution, pas au coût de production."})
        if self.categorie == CategorieCout.STOCKAGE and self.inducteur not in (Inducteur.PALETTES_JOURS, Inducteur.QUANTITE_LIVREE, Inducteur.AUCUN):
            raise ValidationError({"inducteur": "Le stockage se répartit en palettes-jours (ou quantité livrée)."})
        if self.categorie == CategorieCout.DISTRIBUTION and self.inducteur not in (Inducteur.KM, Inducteur.QUANTITE_LIVREE, Inducteur.AUCUN):
            raise ValidationError({"inducteur": "La distribution se répartit au kilomètre ou à la quantité livrée."})
        if self.etape_id and self.etape.hors_cout_production and self.categorie == CategorieCout.PRODUCTION:
            raise ValidationError({"etape": f"L'étape {self.etape.libelle} est hors coût de production."})


class StatutDonnee(models.TextChoices):
    REEL = "REEL", "Réel (mesuré / facturé)"
    ESTIME = "ESTIME", "Estimé"


class StatutRepartition(models.TextChoices):
    A_REPARTIR = "A_REPARTIR", "À répartir"
    REPARTIE = "REPARTIE", "Répartie"
    PARTIELLE = "PARTIELLE", "Partiellement répartie"
    NON_REPARTIE = "NON_REPARTIE", "Non répartie (pas de clé défendable)"


class Charge(ValidationAvantEnregistrement, models.Model):
    """
    Une charge de la période (facture d'électricité, maintenance, pièces,
    salaires, amortissement...). Directe si elle vise un OF, une activité
    (cuve dédiée) ou une tournée ; commune sinon (ex : forage).
    """
    numero = models.CharField("N° charge", max_length=30, unique=True, editable=False)
    nature = models.ForeignKey(NatureCout, verbose_name="Élément de coût", on_delete=models.PROTECT, related_name="charges")
    periode = models.CharField("Période", max_length=7, help_text="AAAA-MM")
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2)
    activite = models.ForeignKey(
        "industriel.Activite", verbose_name="Activité", on_delete=models.PROTECT, null=True, blank=True, related_name="charges",
        help_text="Vide = charge commune à plusieurs activités (répartie par l'inducteur).",
    )
    equipement = models.ForeignKey("industriel.Equipement", verbose_name="Équipement", on_delete=models.PROTECT, null=True, blank=True, related_name="charges")
    ordre_fabrication = models.ForeignKey(
        OrdreFabrication, verbose_name="OF (charge directe)", on_delete=models.PROTECT, null=True, blank=True, related_name="charges_directes",
    )
    tournee = models.ForeignKey("distribution.Tournee", verbose_name="Tournée", on_delete=models.PROTECT, null=True, blank=True, related_name="charges")
    statut_donnee = models.CharField("Donnée", max_length=10, choices=StatutDonnee.choices, default=StatutDonnee.REEL)
    source = models.CharField("Source", max_length=200, blank=True, help_text="Ex : facture SBEE n° 1234, relevé compteur, bulletin de paie.")
    observations = models.TextField("Observations", blank=True)
    statut_repartition = models.CharField("Répartition", max_length=15, choices=StatutRepartition.choices, default=StatutRepartition.A_REPARTIR, editable=False)
    motif_non_repartition = models.TextField("Motif de non-répartition", blank=True, editable=False)
    saisi_par = models.ForeignKey("comptes.Utilisateur", verbose_name="Saisi par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_saisie = models.DateTimeField("Saisie le", auto_now_add=True)

    class Meta:
        verbose_name = "Charge"
        verbose_name_plural = "Charges"
        ordering = ["-periode", "nature"]

    def __str__(self):
        return f"{self.numero} - {self.nature.libelle} {self.periode} : {self.montant}"

    @property
    def est_directe(self):
        return bool(self.ordre_fabrication_id or self.tournee_id or self.activite_id) or self.nature.traitement == Traitement.DIRECT

    def save(self, *args, **kwargs):
        if not self.numero:
            from apps.core.models import generer_numero
            self.numero = generer_numero("CHG")
        super().save(*args, **kwargs)

    def clean(self):
        exiger_positif(self.montant, "montant", "Le montant")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", self.periode or ""):
            raise ValidationError({"periode": "La période doit être au format AAAA-MM (ex : 2026-09)."})
        if self.nature_id and not self.nature.actif:
            raise ValidationError({"nature": f"L'élément de coût « {self.nature.libelle} » est inactif."})
        if self.equipement_id and self.equipement.activite_id:
            if self.activite_id and self.activite_id != self.equipement.activite_id:
                raise ValidationError({"activite": f"{self.equipement.code} est dédié à l'activité {self.equipement.activite.code}."})
            self.activite_id = self.equipement.activite_id   # équipement dédié : charge directe de l'activité
        if self.ordre_fabrication_id:
            of = self.ordre_fabrication
            if of.statut == "ANNULE":
                raise ValidationError({"ordre_fabrication": f"L'OF {of.numero} est annulé."})
            if of.activite and self.activite_id and self.activite_id != of.activite.pk:
                raise ValidationError({"activite": f"L'OF {of.numero} est un OF {of.activite.code}."})
            if self.nature_id and self.nature.categorie != CategorieCout.PRODUCTION:
                raise ValidationError({"ordre_fabrication": "Seule une charge de production s'impute directement à un OF."})
        if self.tournee_id and self.nature_id and self.nature.categorie != CategorieCout.DISTRIBUTION:
            raise ValidationError({"tournee": "Seule une charge de distribution se rattache à une tournée."})
        if self.nature_id and self.nature.traitement == Traitement.DIRECT and self.nature.categorie == CategorieCout.PRODUCTION \
                and not (self.ordre_fabrication_id or self.activite_id) and self.nature.inducteur == Inducteur.AUCUN:
            raise ValidationError({"ordre_fabrication": "Charge directe sans inducteur : précisez l'OF ou l'activité concernée."})


class NiveauRepartition(models.TextChoices):
    ACTIVITE = "ACTIVITE", "Activité"
    OF = "OF", "Ordre de fabrication"
    PRODUIT = "PRODUIT", "Produit / format"
    ARTICLE = "ARTICLE", "Produit (stockage / distribution)"


class RepartitionCout(models.Model):
    """
    Une ligne de la chaîne de calcul (« le logiciel doit conserver la
    chaîne de calcul permettant de retrouver chaque montant ») : montant,
    étape, clé et son unité, valeur totale et part de la clé, quote-part,
    source, réel / estimé / réparti, justification.
    """
    charge = models.ForeignKey(Charge, verbose_name="Charge", on_delete=models.CASCADE, related_name="repartitions")
    parent = models.ForeignKey("self", verbose_name="Niveau supérieur", on_delete=models.CASCADE, null=True, blank=True, related_name="enfants")
    niveau = models.CharField("Niveau", max_length=10, choices=NiveauRepartition.choices)
    activite = models.ForeignKey("industriel.Activite", verbose_name="Activité", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    ordre_fabrication = models.ForeignKey(OrdreFabrication, verbose_name="OF", on_delete=models.CASCADE, null=True, blank=True, related_name="repartitions_couts")
    article = models.ForeignKey(Article, verbose_name="Produit / format", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    etape = models.ForeignKey("industriel.EtapeStandard", verbose_name="Étape", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    inducteur = models.CharField("Clé", max_length=20, choices=Inducteur.choices)
    unite_cle = models.CharField("Unité de la clé", max_length=30, blank=True)
    valeur_cle_totale = models.DecimalField("Valeur totale de la clé", max_digits=18, decimal_places=4, null=True, blank=True)
    valeur_cle_part = models.DecimalField("Valeur de la clé pour ce niveau", max_digits=18, decimal_places=4, null=True, blank=True)
    quote_part = models.DecimalField("Quote-part", max_digits=12, decimal_places=8)
    montant = models.DecimalField("Montant", max_digits=16, decimal_places=2)
    quantite_produite = models.DecimalField("Quantité produite (unités de stock)", max_digits=16, decimal_places=3, null=True, blank=True)
    cout_par_pack = models.DecimalField("Coût par pack", max_digits=16, decimal_places=6, null=True, blank=True)
    cout_par_unite = models.DecimalField("Coût par bouteille / pot", max_digits=16, decimal_places=6, null=True, blank=True)
    statut = models.CharField("Statut", max_length=10, choices=[("REEL", "Réel"), ("ESTIME", "Estimé"), ("REPARTI", "Réparti")])
    source = models.CharField("Source de la donnée", max_length=200, blank=True)
    justification = models.TextField("Justification", blank=True)
    date_calcul = models.DateTimeField("Calculé le", auto_now_add=True)

    class Meta:
        verbose_name = "Répartition de coût"
        verbose_name_plural = "Répartitions de coûts (chaîne de calcul)"
        ordering = ["charge", "niveau", "pk"]

    def __str__(self):
        cible = self.ordre_fabrication or self.article or self.activite
        return f"{self.charge.numero} -> {self.get_niveau_display()} {cible} : {self.montant}"
