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

from django.db import models
from apps.referentiel.models import Article
from apps.production.models import OrdreFabrication


class CoutMatiere(models.Model):
    """Valorisation d'une sortie matière (quantité x coût unitaire de la matière)."""
    article = models.ForeignKey(Article, verbose_name="Matière", on_delete=models.PROTECT)
    cout_unitaire = models.DecimalField("Coût unitaire", max_digits=14, decimal_places=4)
    date_valorisation = models.DateField("Date de valorisation")

    class Meta:
        verbose_name = "Coût matière"
        verbose_name_plural = "Coûts matières"

    def __str__(self):
        return f"{self.article.code} : {self.cout_unitaire}"


class TypeEnergie(models.TextChoices):
    ELECTRICITE = "ELECTRICITE", "Électricité"
    EAU_CAPTAGE = "EAU_CAPTAGE", "Eau / captage-forage"


class CoutEnergie(models.Model):
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


class CoutMainOeuvre(models.Model):
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

    @property
    def cout_total(self):
        return self.heures * self.cout_horaire


class Amortissement(models.Model):
    immobilisation = models.CharField("Immobilisation", max_length=200)
    valeur = models.DecimalField("Valeur d'origine", max_digits=14, decimal_places=2)
    duree_amortissement_mois = models.PositiveIntegerField("Durée d'amortissement (mois)")
    date_debut = models.DateField("Date de début d'amortissement")

    class Meta:
        verbose_name = "Amortissement"
        verbose_name_plural = "Amortissements"

    def __str__(self):
        return self.immobilisation

    @property
    def amortissement_mensuel(self):
        if self.duree_amortissement_mois:
            return self.valeur / self.duree_amortissement_mois
        return 0


class CoutStandard(models.Model):
    """Coût standard de référence d'un article, comparé au coût réel constaté (§13.9)."""
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.CASCADE, related_name="couts_standards")
    cout_standard_unitaire = models.DecimalField("Coût standard unitaire", max_digits=14, decimal_places=4)
    date_debut_validite = models.DateField("Valide à partir du")

    class Meta:
        verbose_name = "Coût standard"
        verbose_name_plural = "Coûts standards"

    def __str__(self):
        return f"Standard {self.article.code} : {self.cout_standard_unitaire}"


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
            + self.cout_energie_total + self.cout_amortissement_total
        )

    @property
    def cout_unitaire_reel(self):
        quantite = self.ordre_fabrication.quantite_a_produire
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

        # 1. Coût matières = (sorties - retours) x dernier coût unitaire connu
        cout_matieres = 0
        matieres_utilisees = (
            SortieMatiere.objects.filter(ordre_fabrication=of)
            .values_list("matiere", flat=True).distinct()
        )
        for matiere_id in matieres_utilisees:
            total_sorti = SortieMatiere.objects.filter(
                ordre_fabrication=of, matiere_id=matiere_id
            ).aggregate(total=Sum("quantite_sortie"))["total"] or 0
            total_retourne = RetourMatiere.objects.filter(
                ordre_fabrication=of, matiere_id=matiere_id
            ).aggregate(total=Sum("quantite_retournee"))["total"] or 0
            consommation_nette = total_sorti - total_retourne

            dernier_cout = (
                CoutMatiere.objects.filter(article_id=matiere_id)
                .order_by("-date_valorisation").first()
            )
            if dernier_cout:
                cout_matieres += consommation_nette * dernier_cout.cout_unitaire

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
        self.save()
        return self
