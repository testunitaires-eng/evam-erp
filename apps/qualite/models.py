# """
# Module 6 - Qualité / Traçabilité.

# Contient le Lot (unité de traçabilité de toute production) et son
# contrôle qualité. Règle centrale du cahier des charges :

#     "Seuls les lots Libérés sont vendables."

# Le statut d'un lot ne peut progresser que dans un sens précis :
# EN_ATTENTE -> (CONFORME ou NON_CONFORME) -> LIBERE ou BLOQUE.
# Le passage à LIBERE est réservé au Responsable Qualité.
# """

# from django.db import models
# from apps.comptes.models import Utilisateur
# from apps.referentiel.models import Article
# from apps.core.models import generer_numero


# class StatutLot(models.TextChoices):
#     EN_ATTENTE = "EN_ATTENTE", "En attente"
#     CONFORME = "CONFORME", "Conforme"
#     NON_CONFORME = "NON_CONFORME", "Non conforme"
#     BLOQUE = "BLOQUE", "Bloqué"
#     LIBERE = "LIBERE", "Libéré"


# class Lot(models.Model):
#     """
#     Un lot = une quantité produite en une fois, traçable de bout en
#     bout (matières utilisées -> OF -> lot -> stock -> commande ->
#     client). Le numéro de lot est unique et généré automatiquement.
#     """
#     numero_lot = models.CharField(
#         "Numéro de lot", max_length=30, unique=True, editable=False
#     )
#     article = models.ForeignKey(
#         Article, verbose_name="Article", on_delete=models.PROTECT,
#         related_name="lots",
#     )
#     ordre_fabrication = models.ForeignKey(
#         "production.OrdreFabrication", verbose_name="Ordre de fabrication",
#         on_delete=models.PROTECT, related_name="lots",
#         null=True, blank=True,
#     )
#     quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
#     statut = models.CharField(
#         "Statut", max_length=20, choices=StatutLot.choices,
#         default=StatutLot.EN_ATTENTE,
#     )
#     date_production = models.DateField("Date de production")
#     date_peremption = models.DateField("Date de péremption", null=True, blank=True)
#     date_creation = models.DateTimeField("Date de création", auto_now_add=True)

#     class Meta:
#         verbose_name = "Lot"
#         verbose_name_plural = "Lots"
#         ordering = ["-date_creation"]

#     def __str__(self):
#         return f"{self.numero_lot} - {self.article.designation} ({self.get_statut_display()})"

#     def save(self, *args, **kwargs):
#         if not self.numero_lot:
#             self.numero_lot = generer_numero("LOT")
#         super().save(*args, **kwargs)

#     @property
#     def est_vendable(self):
#         """Seuls les lots Libérés sont vendables (règle du cahier des charges)."""
#         return self.statut == StatutLot.LIBERE

#     def bloquer(self, motif=""):
#         self.statut = StatutLot.BLOQUE
#         self.save()

#     def liberer(self, utilisateur):
#         """
#         Ne peut être appelé que si le lot est Conforme.
#         La vérification du profil (Responsable Qualité) se fait au
#         niveau de la vue (permission_classes), pas ici.
#         """
#         if self.statut != StatutLot.CONFORME:
#             raise ValueError(
#                 "Seul un lot Conforme peut être libéré. "
#                 "Statut actuel : " + self.get_statut_display()
#             )
#         self.statut = StatutLot.LIBERE
#         self.save()


# class ControleQualite(models.Model):
#     """
#     Le contrôle effectué par le Responsable Qualité sur un lot,
#     qui détermine s'il devient Conforme ou Non conforme.
#     """
#     lot = models.OneToOneField(
#         Lot, verbose_name="Lot contrôlé", on_delete=models.CASCADE,
#         related_name="controle_qualite",
#     )
#     controleur = models.ForeignKey(
#         Utilisateur, verbose_name="Contrôlé par", on_delete=models.PROTECT,
#     )
#     resultat = models.CharField(
#         "Résultat", max_length=20,
#         choices=[("CONFORME", "Conforme"), ("NON_CONFORME", "Non conforme")],
#     )
#     observations = models.TextField("Observations", blank=True)
#     date_controle = models.DateTimeField("Date de contrôle", auto_now_add=True)

#     class Meta:
#         verbose_name = "Contrôle qualité"
#         verbose_name_plural = "Contrôles qualité"

#     def __str__(self):
#         return f"Contrôle {self.lot.numero_lot} - {self.resultat}"

#     def save(self, *args, **kwargs):
#         """A chaque contrôle enregistré, met à jour automatiquement le
#         statut du lot correspondant."""
#         super().save(*args, **kwargs)
#         self.lot.statut = self.resultat
#         self.lot.save()


"""
Module 6 - Qualité / Traçabilité.

Contient le Lot (unité de traçabilité de toute production) et son
contrôle qualité. Règle centrale du cahier des charges :

    "Seuls les lots Libérés sont vendables."

Le statut d'un lot ne peut progresser que dans un sens précis :
EN_ATTENTE -> (CONFORME ou NON_CONFORME) -> LIBERE ou BLOQUE.
Le passage à LIBERE est réservé au Responsable Qualité.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_ordre_dates, valeur_en_base, verifier_transition,
)


class StatutLot(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    CONFORME = "CONFORME", "Conforme"
    NON_CONFORME = "NON_CONFORME", "Non conforme"
    BLOQUE = "BLOQUE", "Bloqué"
    LIBERE = "LIBERE", "Libéré"


class Lot(ValidationAvantEnregistrement, models.Model):
    """
    Un lot = une quantité produite en une fois, traçable de bout en
    bout (matières utilisées -> OF -> lot -> stock -> commande ->
    client). Le numéro de lot est unique et généré automatiquement.
    """
    numero_lot = models.CharField(
        "Numéro de lot", max_length=30, unique=True, editable=False
    )
    article = models.ForeignKey(
        Article, verbose_name="Article", on_delete=models.PROTECT,
        related_name="lots",
    )
    ordre_fabrication = models.ForeignKey(
        "production.OrdreFabrication", verbose_name="Ordre de fabrication",
        on_delete=models.PROTECT, related_name="lots",
        null=True, blank=True,
    )
    quantite = models.DecimalField("Quantité", max_digits=12, decimal_places=3)
    statut = models.CharField(
        "Statut", max_length=20, choices=StatutLot.choices,
        default=StatutLot.EN_ATTENTE,
    )
    date_production = models.DateField("Date de production")
    date_peremption = models.DateField("Date de péremption", null=True, blank=True)
    depot = models.ForeignKey(
        "stocks.Depot", verbose_name="Stock produits finis", on_delete=models.PROTECT, null=True, blank=True,
        related_name="lots_produits_finis", editable=False,
        help_text="Stock usine où le lot entre à sa libération (celui de l'usine de l'OF).",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Lot"
        verbose_name_plural = "Lots"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"{self.numero_lot} - {self.article.designation} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        creation = self._state.adding
        if not self.numero_lot:
            self.numero_lot = generer_numero("LOT")
        if self.depot_id is None:
            from apps.stocks.models import depot_produits_finis
            self.depot = self.ordre_fabrication.depot_produits_finis if self.ordre_fabrication_id else depot_produits_finis()
        with transaction.atomic():
            super().save(*args, **kwargs)
            if creation and self.ordre_fabrication_id:
                generer_controles(self.ordre_fabrication, declencheurs=("CHAQUE_LOT",), lot=self)

    def clean(self):
        """
        - quantité strictement positive, péremption après production ;
        - le lot correspond à l'article de son OF, et un OF annulé ne
          produit pas de lot ;
        - quantité, article et OF ne changent plus une fois le lot
          contrôlé (son contrôle et son entrée en stock en dépendent).
        """
        exiger_positif(self.quantite, "quantite", "La quantité du lot")
        exiger_ordre_dates(
            self.date_production, self.date_peremption, "date_peremption",
            "la date de production", "La date de péremption",
        )
        if self.ordre_fabrication_id:
            of = self.ordre_fabrication
            if of.statut == "ANNULE":
                raise ValidationError({"ordre_fabrication": f"L'OF {of.numero} est annulé : il ne peut pas produire de lot."})
            if self.article_id and of.article_id != self.article_id:
                raise ValidationError({"article": f"L'article du lot doit être celui de l'OF {of.numero}."})
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut not in (None, StatutLot.EN_ATTENTE):
            for champ in ("article", "ordre_fabrication"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Ce lot a déjà été contrôlé : ce champ ne peut plus être modifié."})
            if valeur_en_base(self, "quantite") != self.quantite:
                raise ValidationError({"quantite": "Ce lot a déjà été contrôlé : sa quantité ne peut plus être modifiée."})
        if ancien_statut is None and self.statut != StatutLot.EN_ATTENTE:
            raise ValidationError({"statut": "Un lot est toujours créé « En attente » de contrôle qualité."})

    def verifier_suppression(self):
        if self.statut != StatutLot.EN_ATTENTE:
            raise ValidationError("Seul un lot en attente de contrôle peut être supprimé.")

    @property
    def lieu_stock(self):
        if self.depot_id:
            return self.depot
        from apps.stocks.models import depot_produits_finis
        return depot_produits_finis()

    @property
    def est_vendable(self):
        """Seuls les lots Libérés sont vendables (règle du cahier des charges)."""
        return self.statut == StatutLot.LIBERE

    @transaction.atomic
    def bloquer(self, motif=""):
        """
        Bloque le lot. S'il était déjà libéré (donc entré en stock
        produits finis), sa quantité passe en « bloquée » dans ce stock :
        elle n'est plus disponible à la vente ni à la sortie.
        """
        if self.statut == StatutLot.BLOQUE:
            raise ValueError("Ce lot est déjà bloqué.")
        if self.statut == StatutLot.LIBERE:
            from apps.stocks.models import StockArticle
            stock = StockArticle.objects.select_for_update().filter(
                article=self.article, depot=self.lieu_stock,
            ).first()
            if stock is None or stock.quantite_disponible < self.quantite:
                disponible = stock.quantite_disponible if stock else 0
                raise ValueError(
                    f"Impossible de bloquer le lot {self.numero_lot} : il n'en reste que {disponible} "
                    f"disponible(s) en stock produits finis sur {self.quantite} (le reste a déjà été vendu/sorti)."
                )
            stock.quantite_bloquee += self.quantite
            stock.save()
        self.statut = StatutLot.BLOQUE
        self.save()

    @transaction.atomic
    def liberer(self, utilisateur):
        """
        Ne peut être appelé que si le lot est Conforme.
        La vérification du profil (Responsable Qualité) se fait au
        niveau de la vue (permission_classes), pas ici.

        La libération est le moment où le produit fini devient
        vendable (règle centrale du module) : elle doit donc faire
        ENTRER physiquement la quantité du lot dans le stock des
        produits finis, sans quoi aucune commande client ne pourrait
        jamais réserver/sortir ce lot alors même qu'il est "libéré".
        """
        if self.statut != StatutLot.CONFORME:
            raise ValueError(
                "Seul un lot Conforme peut être libéré. "
                "Statut actuel : " + self.get_statut_display()
            )
        blocages = blocages_qualite_lot(self)
        if blocages:
            raise ValueError(f"Libération du lot {self.numero_lot} impossible : " + " ; ".join(blocages) + ".")
        self.statut = StatutLot.LIBERE
        self.save()
        from apps.stocks.models import MouvementStock, TypeMouvement
        # Le produit fini entre en stock à son COÛT DE REVIENT réel (OF).
        cout_unitaire = None
        if self.ordre_fabrication_id:
            from apps.couts.models import CoutReel
            cout_reel, _ = CoutReel.objects.get_or_create(ordre_fabrication=self.ordre_fabrication)
            cout_reel.calculer()
            cout_unitaire = cout_reel.cout_unitaire_reel or None
        MouvementStock.objects.create(
            article=self.article,
            depot=self.lieu_stock,
            type_mouvement=TypeMouvement.ENTREE,
            quantite=self.quantite,
            cout_unitaire=cout_unitaire,
            motif=f"Libération qualité du lot {self.numero_lot}",
            document_origine=self.numero_lot,
            utilisateur=utilisateur,
        )


class ControleQualite(ValidationAvantEnregistrement, models.Model):
    """
    Le contrôle effectué par le Responsable Qualité sur un lot,
    qui détermine s'il devient Conforme ou Non conforme.
    """
    lot = models.OneToOneField(
        Lot, verbose_name="Lot contrôlé", on_delete=models.CASCADE,
        related_name="controle_qualite",
    )
    controleur = models.ForeignKey(
        Utilisateur, verbose_name="Contrôlé par", on_delete=models.PROTECT,
    )
    resultat = models.CharField(
        "Résultat", max_length=20,
        choices=[("CONFORME", "Conforme"), ("NON_CONFORME", "Non conforme")],
    )
    observations = models.TextField("Observations", blank=True)
    date_controle = models.DateTimeField("Date de contrôle", auto_now_add=True)

    class Meta:
        verbose_name = "Contrôle qualité"
        verbose_name_plural = "Contrôles qualité"

    def __str__(self):
        return f"Contrôle {self.lot.numero_lot} - {self.resultat}"

    def clean(self):
        """
        Un lot libéré ou bloqué ne peut plus être (re)contrôlé :
        auparavant, modifier le contrôle d'un lot libéré le remettait à
        « Conforme », et on pouvait le libérer une 2e fois (double
        entrée en stock).
        """
        if self.pk and valeur_en_base(self, "lot") != self.lot_id:
            raise ValidationError({"lot": "Le lot d'un contrôle ne peut pas être changé."})
        if self.lot_id and self.lot.statut in (StatutLot.LIBERE, StatutLot.BLOQUE):
            raise ValidationError({"lot": (
                f"Le lot {self.lot.numero_lot} est {self.lot.get_statut_display().lower()} : "
                "son contrôle ne peut plus être créé ni modifié."
            )})
        if self.lot_id and self.resultat == "CONFORME":
            blocages = blocages_qualite_lot(self.lot)
            if blocages:
                raise ValidationError({"resultat": "Le lot ne peut pas être déclaré conforme : " + " ; ".join(blocages) + "."})

    def verifier_suppression(self):
        if self.lot.statut in (StatutLot.LIBERE, StatutLot.BLOQUE):
            raise ValidationError("Le lot est déjà libéré ou bloqué : son contrôle ne peut plus être supprimé.")

    def save(self, *args, **kwargs):
        """A chaque contrôle enregistré, met à jour automatiquement le
        statut du lot correspondant."""
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.lot.statut = self.resultat
            self.lot.save()


# =====================================================================
# Module Contrôle qualité (documents « Contrôle qualité — Eau / Jus /
# Yaourt », schéma « Élargissement de l'onglet contrôle qualité ») :
#   1. paramétrage (paramètres, instruments)   2. plan de contrôle
#   3. contrôles à réaliser (générés)          4. saisie des résultats
#   5. non-conformités                          6. suivi / indicateurs
# Règle : aucune valeur cible, seuil, fréquence ou caractère bloquant
# n'est inventé par le logiciel ; tout vient du paramétrage, renseigné à
# partir des fiches qualité validées de l'usine.
# =====================================================================

class FamilleParametre(models.TextChoices):
    PHYSICO_CHIMIQUE = "PHYSICO_CHIMIQUE", "Physico-chimique"
    MICROBIOLOGIQUE = "MICROBIOLOGIQUE", "Microbiologique"
    ORGANOLEPTIQUE = "ORGANOLEPTIQUE", "Organoleptique (aspect, couleur, goût)"
    PROCESS = "PROCESS", "Paramètre de process (débit, pression, température...)"
    CONDITIONNEMENT = "CONDITIONNEMENT", "Conditionnement (volume, bouchage, étiquetage, pack)"
    MATIERE = "MATIERE", "Matière / réception"
    DOCUMENTAIRE = "DOCUMENTAIRE", "Documentaire (documents fournisseur...)"


class TypeResultat(models.TextChoices):
    NUMERIQUE = "NUMERIQUE", "Valeur mesurée"
    QUALITATIF = "QUALITATIF", "Conforme / non conforme"


class ParametreQualite(ValidationAvantEnregistrement, models.Model):
    """Ce qui se mesure ou s'observe : pH, °Brix, température, serrage bouchon, présence étiquette..."""
    code = models.CharField("Code", max_length=30, unique=True, editable=False)
    libelle = models.CharField("Paramètre", max_length=100)
    famille = models.CharField("Famille", max_length=20, choices=FamilleParametre.choices)
    type_resultat = models.CharField("Type de résultat", max_length=12, choices=TypeResultat.choices, default=TypeResultat.NUMERIQUE)
    unite = models.CharField("Unité", max_length=30, blank=True, help_text="Ex : pH, °Brix, °C, mL, N·m, UFC/mL.")
    methode = models.CharField("Méthode par défaut", max_length=200, blank=True)
    poids_analyse = models.DecimalField(
        "Poids de l'analyse", max_digits=8, decimal_places=2, default=1,
        help_text="Clé « analyses pondérées » du coût laboratoire : une analyse microbiologique pèse plus qu'un pH.",
    )
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Paramètre qualité"
        verbose_name_plural = "Paramètres qualité"
        ordering = ["famille", "libelle"]

    def __str__(self):
        unite = f" ({self.unite})" if self.unite else ""
        return f"{self.libelle}{unite}"

    def save(self, *args, **kwargs):
        if not self.code:
            from apps.core.models import generer_code_unique
            self.code = generer_code_unique(ParametreQualite, "PAR", largeur=3)
        super().save(*args, **kwargs)

    def clean(self):
        if not (self.libelle or "").strip():
            raise ValidationError({"libelle": "Le libellé du paramètre est obligatoire."})
        exiger_positif(self.poids_analyse, "poids_analyse", "Le poids de l'analyse")
        if self.type_resultat == TypeResultat.NUMERIQUE and not (self.unite or "").strip():
            raise ValidationError({"unite": "Un paramètre mesuré a une unité (pH, °Brix, °C...)."})


class Laboratoire(models.TextChoices):
    LIGNE = "LIGNE", "Sur ligne (opérateur)"
    INTERNE = "INTERNE", "Laboratoire interne"
    EXTERNE = "EXTERNE", "Laboratoire externe"


class Instrument(ValidationAvantEnregistrement, models.Model):
    """Appareil de mesure (pH-mètre, réfractomètre, thermomètre...) et son étalonnage."""
    code = models.CharField("Code", max_length=30, unique=True, editable=False)
    designation = models.CharField("Désignation", max_length=100)
    numero_serie = models.CharField("N° appareil / série", max_length=60, blank=True)
    laboratoire = models.CharField("Utilisé", max_length=10, choices=Laboratoire.choices, default=Laboratoire.LIGNE)
    date_dernier_etalonnage = models.DateField("Dernier étalonnage / vérification", null=True, blank=True)
    periodicite_etalonnage_jours = models.PositiveIntegerField(
        "Périodicité d'étalonnage (jours)", null=True, blank=True, help_text="Vide = pas d'étalonnage suivi.",
    )
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Instrument de mesure"
        verbose_name_plural = "Instruments de mesure"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.code:
            from apps.core.models import generer_code_unique
            self.code = generer_code_unique(Instrument, "INS", largeur=3)
        super().save(*args, **kwargs)

    def clean(self):
        if self.periodicite_etalonnage_jours == 0:
            raise ValidationError({"periodicite_etalonnage_jours": "La périodicité doit être supérieure à 0 (vide si non suivie)."})

    @property
    def prochaine_echeance(self):
        from datetime import timedelta
        if not self.periodicite_etalonnage_jours:
            return None
        if not self.date_dernier_etalonnage:
            return None
        return self.date_dernier_etalonnage + timedelta(days=self.periodicite_etalonnage_jours)

    @property
    def etalonnage_valide(self):
        """False si l'étalonnage est suivi et dépassé (ou jamais fait)."""
        from django.utils import timezone
        if not self.periodicite_etalonnage_jours:
            return True
        echeance = self.prochaine_echeance
        return echeance is not None and echeance >= timezone.localdate()


class Declencheur(models.TextChoices):
    RECEPTION = "RECEPTION", "À la réception (lot matière)"
    DEMARRAGE = "DEMARRAGE", "Au démarrage de l'OF"
    CHAQUE_OF = "CHAQUE_OF", "Une fois par OF"
    CHAQUE_LOT = "CHAQUE_LOT", "À chaque lot de produit fini"
    PERIODIQUE = "PERIODIQUE", "Toutes les X minutes pendant la production"
    CHANGEMENT_SERIE = "CHANGEMENT_SERIE", "Après chaque changement de série"
    PONCTUEL = "PONCTUEL", "Ponctuel (à la demande)"


class StatutPointControle(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    ACTIF = "ACTIF", "Actif"
    INACTIF = "INACTIF", "Inactif"


class PointControle(ValidationAvantEnregistrement, models.Model):
    """
    Une ligne du PLAN DE CONTRÔLE : quel paramètre contrôler, où (étape,
    poste, machine, point de prélèvement), pour quoi (activité, format,
    recette), selon quels critères (cible, min, max, tolérance), quand
    (déclencheur, fréquence), comment (échantillon, méthode, instrument)
    et avec quelle conséquence (bloquant ou non, actions en cas de NC).
    """
    code = models.CharField("Code du contrôle", max_length=30, unique=True, editable=False)
    designation = models.CharField("Désignation", max_length=150)
    parametre = models.ForeignKey(ParametreQualite, verbose_name="Paramètre contrôlé", on_delete=models.PROTECT, related_name="points")
    # Où / pour quoi
    activite = models.ForeignKey(
        "industriel.Activite", verbose_name="Activité", on_delete=models.PROTECT, null=True, blank=True,
        related_name="points_controle", help_text="Vide uniquement pour un contrôle de réception de matière.",
    )
    article = models.ForeignKey(
        Article, verbose_name="Produit / format ou matière", on_delete=models.PROTECT, null=True, blank=True,
        related_name="points_controle", help_text="Vide = tous les formats de l'activité.",
    )
    fiche_technique = models.ForeignKey(
        "referentiel.FicheTechnique", verbose_name="Recette (version)", on_delete=models.PROTECT, null=True, blank=True,
        related_name="points_controle",
    )
    etape = models.ForeignKey("industriel.EtapeStandard", verbose_name="Étape du circuit", on_delete=models.PROTECT, null=True, blank=True, related_name="points_controle")
    poste = models.ForeignKey("industriel.Poste", verbose_name="Poste", on_delete=models.PROTECT, null=True, blank=True)
    equipement = models.ForeignKey("industriel.Equipement", verbose_name="Machine / équipement (forage, cuve...)", on_delete=models.PROTECT, null=True, blank=True)
    point_prelevement = models.CharField("Point de prélèvement", max_length=150, blank=True, help_text="Ex : avant filtration, sortie UV, cuve tampon.")
    # Critères
    valeur_cible = models.DecimalField("Valeur cible", max_digits=14, decimal_places=4, null=True, blank=True)
    valeur_min = models.DecimalField("Valeur minimale", max_digits=14, decimal_places=4, null=True, blank=True)
    valeur_max = models.DecimalField("Valeur maximale", max_digits=14, decimal_places=4, null=True, blank=True)
    tolerance = models.DecimalField("Tolérance (±)", max_digits=14, decimal_places=4, null=True, blank=True)
    bloquant = models.BooleanField(
        "Contrôle bloquant", default=False,
        help_text="Un résultat non conforme bloque le lot et empêche la clôture de l'OF tant que la NC n'est pas traitée.",
    )
    # Quand
    declencheur = models.CharField("Fréquence / déclenchement", max_length=20, choices=Declencheur.choices)
    frequence_minutes = models.PositiveIntegerField("Toutes les (minutes)", null=True, blank=True)
    # Comment
    type_echantillon = models.CharField("Type d'échantillon", max_length=100, blank=True)
    quantite_echantillon = models.CharField("Quantité d'échantillon", max_length=50, blank=True)
    nombre_echantillons = models.PositiveIntegerField("Nombre d'échantillons", default=1)
    echantillon_conserve = models.BooleanField("Échantillon témoin conservé", default=False)
    methode = models.CharField("Méthode", max_length=200, blank=True)
    instrument = models.ForeignKey(Instrument, verbose_name="Instrument", on_delete=models.PROTECT, null=True, blank=True, related_name="points")
    laboratoire = models.CharField("Réalisé", max_length=10, choices=Laboratoire.choices, default=Laboratoire.LIGNE)
    actions_si_non_conforme = models.TextField(
        "Actions en cas de non-conformité", blank=True,
        help_text="Ex : arrêt, nouveau contrôle, contre-analyse, réglage machine, blocage lot, rejet, quarantaine.",
    )
    document_reference = models.CharField("Procédure / fiche de référence", max_length=200, blank=True)
    # Version
    version = models.PositiveIntegerField("Version", default=1)
    statut = models.CharField("Statut", max_length=10, choices=StatutPointControle.choices, default=StatutPointControle.BROUILLON)
    date_debut = models.DateField("Applicable à partir du", null=True, blank=True)
    date_fin = models.DateField("Applicable jusqu'au", null=True, blank=True)

    class Meta:
        verbose_name = "Point du plan de contrôle"
        verbose_name_plural = "Plan de contrôle"
        ordering = ["activite", "etape__ordre_reference", "code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.code:
            from apps.core.models import generer_code_unique
            prefixe = f"CTL-{self.activite.code}" if self.activite_id else "CTL-REC"
            self.code = generer_code_unique(PointControle, prefixe, largeur=3)
        super().save(*args, **kwargs)

    def clean(self):
        from apps.core.validation import exiger_ordre_dates
        if self.declencheur == Declencheur.PERIODIQUE and not self.frequence_minutes:
            raise ValidationError({"frequence_minutes": "Indiquez la fréquence (en minutes) d'un contrôle périodique."})
        if self.declencheur == Declencheur.RECEPTION:
            if not self.article_id:
                raise ValidationError({"article": "Un contrôle de réception porte sur un article (matière, emballage...)."})
            if self.article.type_article == "PRODUIT_FINI":
                raise ValidationError({"article": "Un contrôle de réception porte sur un article acheté, pas un produit fini."})
        elif not self.activite_id:
            raise ValidationError({"activite": "L'activité est obligatoire (sauf contrôle de réception)."})
        if self.article_id and self.activite_id and self.declencheur != Declencheur.RECEPTION \
                and self.article.activite_id and self.article.activite_id != self.activite_id:
            raise ValidationError({"article": f"{self.article.code} n'appartient pas à l'activité {self.activite.code}."})
        if self.fiche_technique_id and self.article_id and self.fiche_technique.article_id != self.article_id \
                and not self.fiche_technique.formats_associes.filter(pk=self.article_id).exists():
            raise ValidationError({"fiche_technique": "Cette recette ne concerne pas ce produit."})
        if self.poste_id and self.etape_id and self.poste.etape_id != self.etape_id:
            raise ValidationError({"poste": f"Le poste {self.poste.code} ne réalise pas l'étape {self.etape.libelle}."})
        if self.equipement_id and self.activite_id and self.equipement.activite_id \
                and self.equipement.activite_id != self.activite_id:
            raise ValidationError({"equipement": f"{self.equipement.code} est dédié à une autre activité."})
        exiger_ordre_dates(self.date_debut, self.date_fin, "date_fin", "le début d'application", "La fin d'application")
        if self.valeur_min is not None and self.valeur_max is not None and self.valeur_min > self.valeur_max:
            raise ValidationError({"valeur_max": "La valeur maximale doit être supérieure ou égale à la valeur minimale."})
        if self.tolerance is not None and self.tolerance < 0:
            raise ValidationError({"tolerance": "La tolérance ne peut pas être négative."})
        if self.tolerance is not None and self.valeur_cible is None:
            raise ValidationError({"valeur_cible": "Une tolérance s'applique autour d'une valeur cible."})
        if self.nombre_echantillons == 0:
            raise ValidationError({"nombre_echantillons": "Au moins un échantillon."})
        if self.statut == StatutPointControle.ACTIF and self.parametre_id \
                and self.parametre.type_resultat == TypeResultat.NUMERIQUE and not self.a_des_criteres:
            raise ValidationError({"valeur_min": (
                "Un contrôle mesuré ne peut être activé qu'avec ses critères d'acceptation (min/max ou cible ± tolérance), "
                "repris de la fiche qualité validée."
            )})
        ancien = valeur_en_base(self, "statut")
        if ancien and ancien != StatutPointControle.BROUILLON and self.pk and ResultatControle.objects.filter(point_id=self.pk).exists():
            for champ in ("valeur_cible", "valeur_min", "valeur_max", "tolerance", "parametre", "bloquant"):
                attribut = f"{champ}_id" if champ == "parametre" else champ
                if valeur_en_base(self, champ) != getattr(self, attribut):
                    raise ValidationError({champ: (
                        "Ce contrôle a déjà des résultats : ses critères ne changent plus (historique). "
                        "Désactivez-le et créez une nouvelle version."
                    )})

    def verifier_suppression(self):
        if self.resultats.exists():
            raise ValidationError("Ce contrôle a déjà des résultats : désactivez-le plutôt.")

    @property
    def a_des_criteres(self):
        return self.valeur_min is not None or self.valeur_max is not None or (
            self.valeur_cible is not None and self.tolerance is not None
        )

    def est_conforme(self, valeur):
        """Conformité calculée automatiquement (ex : pH 3,6 pour 3,2 - 3,8 -> conforme). None si aucun critère."""
        from decimal import Decimal
        if not self.a_des_criteres:
            return None
        valeur = Decimal(valeur)
        if self.valeur_min is not None and valeur < self.valeur_min:
            return False
        if self.valeur_max is not None and valeur > self.valeur_max:
            return False
        if self.valeur_cible is not None and self.tolerance is not None and abs(valeur - self.valeur_cible) > self.tolerance:
            return False
        return True

    def nouvelle_version(self):
        """Copie (brouillon, version + 1) ; l'ancienne version est désactivée."""
        champs = {
            champ.name: getattr(self, champ.name) for champ in self._meta.fields
            if champ.name not in ("id", "code", "version", "statut")
        }
        copie = PointControle(**champs, version=self.version + 1, statut=StatutPointControle.BROUILLON)
        copie.save()
        self.statut = StatutPointControle.INACTIF
        self.save()
        return copie


class StatutResultat(models.TextChoices):
    A_REALISER = "A_REALISER", "À réaliser"
    EN_ATTENTE_VALIDATION = "EN_ATTENTE_VALIDATION", "En attente de validation (laboratoire)"
    CONFORME = "CONFORME", "Conforme"
    NON_CONFORME = "NON_CONFORME", "Non conforme"
    ANNULE = "ANNULE", "Annulé"


STATUTS_EN_ATTENTE = (StatutResultat.A_REALISER, StatutResultat.EN_ATTENTE_VALIDATION)


class ResultatControle(ValidationAvantEnregistrement, models.Model):
    """
    Un contrôle à réaliser puis réalisé. Le contexte (OF, produit, lot,
    ligne, poste, machine, étape) est repris automatiquement ; la
    conformité est calculée à partir des critères du plan.
    """
    numero = models.CharField("N° contrôle", max_length=30, unique=True, editable=False)
    point = models.ForeignKey(PointControle, verbose_name="Contrôle (plan)", on_delete=models.PROTECT, related_name="resultats")
    ordre_fabrication = models.ForeignKey(
        "production.OrdreFabrication", verbose_name="OF", on_delete=models.PROTECT, null=True, blank=True, related_name="controles_qualite",
    )
    lot = models.ForeignKey(Lot, verbose_name="Lot produit fini", on_delete=models.PROTECT, null=True, blank=True, related_name="resultats_controles")
    lot_matiere = models.ForeignKey(
        "stocks.LotMatiere", verbose_name="Lot matière / emballage", on_delete=models.PROTECT, null=True, blank=True, related_name="resultats_controles",
    )
    article = models.ForeignKey(Article, verbose_name="Produit / matière", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    ligne = models.ForeignKey("industriel.Ligne", verbose_name="Ligne", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    etape = models.ForeignKey("industriel.EtapeStandard", verbose_name="Étape", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    poste = models.ForeignKey("industriel.Poste", verbose_name="Poste", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    equipement = models.ForeignKey("industriel.Equipement", verbose_name="Machine", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    statut = models.CharField("Statut", max_length=25, choices=StatutResultat.choices, default=StatutResultat.A_REALISER)
    date_prevue = models.DateTimeField("Prévu le", null=True, blank=True)
    date_realisation = models.DateTimeField("Réalisé le", null=True, blank=True)
    valeur = models.DecimalField("Valeur mesurée", max_digits=14, decimal_places=4, null=True, blank=True)
    resultat_qualitatif = models.CharField(
        "Résultat observé", max_length=15, blank=True,
        choices=[("CONFORME", "Conforme"), ("NON_CONFORME", "Non conforme")],
        help_text="Pour un contrôle visuel / qualitatif.",
    )
    conforme = models.BooleanField("Conforme", null=True, blank=True, editable=False)
    instrument = models.ForeignKey(Instrument, verbose_name="Instrument utilisé", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reference_echantillon = models.CharField("Référence de l'échantillon", max_length=60, blank=True)
    operateur = models.ForeignKey(Utilisateur, verbose_name="Opérateur", on_delete=models.PROTECT, null=True, blank=True, related_name="controles_realises")
    valide_par = models.ForeignKey(Utilisateur, verbose_name="Validé par (qualité)", on_delete=models.PROTECT, null=True, blank=True, related_name="controles_valides")
    commentaire = models.TextField("Commentaire", blank=True)
    est_reprise = models.BooleanField("Contrôle de reprise", default=False)
    controle_origine = models.ForeignKey(
        "self", verbose_name="Contrôle d'origine (reprise)", on_delete=models.PROTECT, null=True, blank=True, related_name="reprises",
    )
    date_creation = models.DateTimeField("Créé le", auto_now_add=True)

    class Meta:
        verbose_name = "Contrôle qualité réalisé"
        verbose_name_plural = "Contrôles qualité réalisés"
        ordering = ["-date_prevue", "-pk"]

    def __str__(self):
        return f"{self.numero} - {self.point.designation} ({self.get_statut_display()})"

    TRANSITIONS = {
        StatutResultat.A_REALISER: {
            StatutResultat.EN_ATTENTE_VALIDATION, StatutResultat.CONFORME, StatutResultat.NON_CONFORME, StatutResultat.ANNULE,
        },
        StatutResultat.EN_ATTENTE_VALIDATION: {StatutResultat.CONFORME, StatutResultat.NON_CONFORME, StatutResultat.ANNULE},
    }

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("CQ")
        self.completer_contexte()
        super().save(*args, **kwargs)

    def completer_contexte(self):
        """Récupération automatique du contexte (OF -> produit -> ligne ; plan -> étape, poste, machine)."""
        if self.lot_id and not self.ordre_fabrication_id:
            self.ordre_fabrication_id = self.lot.ordre_fabrication_id
        of = self.ordre_fabrication if self.ordre_fabrication_id else None
        if not self.article_id:
            self.article_id = (
                of.article_id if of else self.lot.article_id if self.lot_id
                else self.lot_matiere.article_id if self.lot_matiere_id else self.point.article_id
            )
        if of and not self.ligne_id:
            self.ligne_id = of.ligne_id
        for champ in ("etape", "poste", "equipement"):
            if not getattr(self, f"{champ}_id"):
                setattr(self, f"{champ}_id", getattr(self.point, f"{champ}_id"))
        if not self.instrument_id and self.point.instrument_id:
            self.instrument_id = self.point.instrument_id

    def clean(self):
        ancien = valeur_en_base(self, "statut")
        if ancien in (StatutResultat.CONFORME, StatutResultat.NON_CONFORME, StatutResultat.ANNULE):
            raise ValidationError(f"Le contrôle {self.numero} est {self.get_statut_display().lower()} : il est figé (historique).")
        verifier_transition(ancien, self.statut, self.TRANSITIONS, "statut du contrôle", initial=StatutResultat.A_REALISER)
        if self.ordre_fabrication_id and self.ordre_fabrication.est_verrouille and ancien is None:
            raise ValidationError({"ordre_fabrication": f"L'OF {self.ordre_fabrication.numero} est clôturé ou annulé."})
        if self.lot_id and self.ordre_fabrication_id and self.lot.ordre_fabrication_id not in (None, self.ordre_fabrication_id):
            raise ValidationError({"lot": "Ce lot appartient à un autre OF."})
        if self.point_id and self.point.declencheur == Declencheur.RECEPTION and not self.lot_matiere_id:
            raise ValidationError({"lot_matiere": "Un contrôle de réception porte sur un lot matière."})
        if self.point_id and self.point.declencheur != Declencheur.RECEPTION and not (self.ordre_fabrication_id or self.lot_id):
            raise ValidationError({"ordre_fabrication": "Un contrôle de production est rattaché à un OF ou à un lot."})
        if self.controle_origine_id:
            if self.controle_origine.point_id != self.point_id:
                raise ValidationError({"controle_origine": "Une reprise porte sur le même contrôle du plan."})
            self.est_reprise = True

    def verifier_suppression(self):
        raise ValidationError("Un contrôle qualité ne se supprime pas : annulez-le (avec un commentaire).")

    @transaction.atomic
    def enregistrer(self, operateur, valeur=None, resultat_qualitatif="", instrument=None, commentaire="",
                    reference_echantillon="", valide_par=None):
        """
        Saisie du résultat : conformité calculée selon le plan (valeur
        mesurée) ou résultat observé (contrôle visuel). Un résultat non
        conforme ouvre automatiquement une non-conformité ; si le contrôle
        est bloquant, le lot est bloqué.
        """
        from django.utils import timezone
        from apps.core.validation import convertir_decimal
        if self.statut not in STATUTS_EN_ATTENTE:
            raise ValueError(f"Le contrôle {self.numero} est déjà {self.get_statut_display().lower()}.")
        point = self.point
        if instrument is not None:
            self.instrument = instrument
        if self.instrument_id and not self.instrument.etalonnage_valide:
            raise ValueError(
                f"L'instrument {self.instrument.code} n'est pas étalonné (échéance {self.instrument.prochaine_echeance or 'jamais réalisé'}) : "
                "mesure refusée."
            )
        if point.parametre.type_resultat == TypeResultat.NUMERIQUE:
            self.valeur = convertir_decimal(valeur, "La valeur mesurée", strict=False) if valeur not in (None, "") else None
            if self.valeur is None:
                raise ValueError(f"Saisissez la valeur mesurée ({point.parametre.unite}).")
            conforme = point.est_conforme(self.valeur)
            if conforme is None:
                if resultat_qualitatif not in ("CONFORME", "NON_CONFORME"):
                    raise ValueError("Ce contrôle n'a pas de critère chiffré au plan : indiquez le résultat (conforme / non conforme).")
                conforme = resultat_qualitatif == "CONFORME"
        else:
            if resultat_qualitatif not in ("CONFORME", "NON_CONFORME"):
                raise ValueError("Indiquez le résultat observé : CONFORME ou NON_CONFORME.")
            conforme = resultat_qualitatif == "CONFORME"
        self.resultat_qualitatif = resultat_qualitatif or ("CONFORME" if conforme else "NON_CONFORME")
        self.conforme = conforme
        self.statut = StatutResultat.CONFORME if conforme else StatutResultat.NON_CONFORME
        self.operateur = operateur
        self.valide_par = valide_par
        self.commentaire = commentaire or self.commentaire
        self.reference_echantillon = reference_echantillon or self.reference_echantillon
        self.date_realisation = timezone.now()
        self.save()
        if not conforme:
            NonConformite.ouvrir_depuis(self, operateur)
        else:
            self._apres_conformite()
        self._programmer_suivant()
        return self

    def soumettre_au_laboratoire(self, operateur, reference_echantillon=""):
        """Échantillon envoyé au laboratoire : en attente du résultat."""
        if self.statut != StatutResultat.A_REALISER:
            raise ValueError("Seul un contrôle à réaliser peut être envoyé au laboratoire.")
        self.statut = StatutResultat.EN_ATTENTE_VALIDATION
        self.operateur = operateur
        self.reference_echantillon = reference_echantillon or self.reference_echantillon
        self.save()

    def annuler(self, motif):
        if not (motif or "").strip():
            raise ValueError("Le motif d'annulation est obligatoire.")
        if self.statut not in STATUTS_EN_ATTENTE:
            raise ValueError("Un contrôle réalisé ne s'annule pas (historique).")
        self.statut = StatutResultat.ANNULE
        self.commentaire = f"Annulé : {motif.strip()}"
        self.save()

    def _apres_conformite(self):
        """Lot matière : tous ses contrôles de réception conformes -> libéré."""
        from apps.stocks.models import StatutLotMatiere
        lot = self.lot_matiere
        if lot is None or lot.statut != StatutLotMatiere.A_CONTROLER:
            return
        restants = ResultatControle.objects.filter(lot_matiere=lot).exclude(statut__in=(StatutResultat.CONFORME, StatutResultat.ANNULE))
        if not restants.exists() and not NonConformite.objects.filter(lot_matiere=lot).exclude(statut=StatutNC.CLOTUREE).exists():
            lot.changer_statut(StatutLotMatiere.LIBERE)

    def _programmer_suivant(self):
        """Contrôle périodique : le suivant est planifié tant que l'OF est en production."""
        from datetime import timedelta
        point, of = self.point, self.ordre_fabrication
        if point.declencheur != Declencheur.PERIODIQUE or of is None or of.statut != "EN_PRODUCTION" or self.est_reprise:
            return
        ResultatControle.objects.create(
            point=point, ordre_fabrication=of, lot=self.lot,
            date_prevue=self.date_realisation + timedelta(minutes=point.frequence_minutes),
        )

    def creer_reprise(self):
        """Contrôle de reprise (nouveau contrôle / contre-analyse) après une non-conformité."""
        from django.utils import timezone
        if self.statut != StatutResultat.NON_CONFORME:
            raise ValueError("Une reprise ne s'ouvre que sur un contrôle non conforme.")
        return ResultatControle.objects.create(
            point=self.point, ordre_fabrication=self.ordre_fabrication, lot=self.lot, lot_matiere=self.lot_matiere,
            controle_origine=self, est_reprise=True, date_prevue=timezone.now(),
        )


class StatutNC(models.TextChoices):
    OUVERTE = "OUVERTE", "Ouverte"
    EN_COURS = "EN_COURS", "Action en cours"
    CLOTUREE = "CLOTUREE", "Clôturée"


class ActionImmediate(models.TextChoices):
    ALERTE = "ALERTE", "Alerte"
    ARRET = "ARRET", "Arrêt production"
    BLOCAGE_LOT = "BLOCAGE_LOT", "Blocage du lot"
    NOUVEAU_CONTROLE = "NOUVEAU_CONTROLE", "Nouveau contrôle"
    CONTRE_ANALYSE = "CONTRE_ANALYSE", "Contre-analyse"
    REGLAGE = "REGLAGE", "Réglage machine"
    NETTOYAGE = "NETTOYAGE", "Nettoyage / désinfection"
    CORRECTION_FORMULATION = "CORRECTION_FORMULATION", "Correction de formulation"
    QUARANTAINE = "QUARANTAINE", "Quarantaine"


class DecisionNC(models.TextChoices):
    LIBERATION = "LIBERATION", "Libération (reprise conforme)"
    REPRISE = "REPRISE", "Reprise / retraitement"
    REJET = "REJET", "Rejet"
    QUARANTAINE = "QUARANTAINE", "Maintien en quarantaine"


class NonConformite(ValidationAvantEnregistrement, models.Model):
    """Non-conformité : cause, action immédiate, action corrective, responsable, suivi et clôture."""
    numero = models.CharField("N° NC", max_length=30, unique=True, editable=False)
    resultat = models.ForeignKey(ResultatControle, verbose_name="Contrôle à l'origine", on_delete=models.PROTECT, null=True, blank=True, related_name="non_conformites")
    ordre_fabrication = models.ForeignKey("production.OrdreFabrication", verbose_name="OF", on_delete=models.PROTECT, null=True, blank=True, related_name="non_conformites")
    lot = models.ForeignKey(Lot, verbose_name="Lot produit fini", on_delete=models.PROTECT, null=True, blank=True, related_name="non_conformites")
    lot_matiere = models.ForeignKey("stocks.LotMatiere", verbose_name="Lot matière", on_delete=models.PROTECT, null=True, blank=True, related_name="non_conformites")
    description = models.TextField("Description")
    bloquante = models.BooleanField("Bloquante", default=False)
    cause = models.TextField("Cause", blank=True)
    action_immediate = models.CharField("Action immédiate", max_length=25, choices=ActionImmediate.choices, blank=True)
    action_corrective = models.TextField("Action corrective", blank=True)
    responsable = models.ForeignKey(Utilisateur, verbose_name="Responsable de l'action", on_delete=models.PROTECT, null=True, blank=True, related_name="nc_a_traiter")
    echeance = models.DateField("Échéance", null=True, blank=True)
    statut = models.CharField("Statut", max_length=10, choices=StatutNC.choices, default=StatutNC.OUVERTE)
    decision = models.CharField("Décision", max_length=15, choices=DecisionNC.choices, blank=True)
    ouverte_par = models.ForeignKey(Utilisateur, verbose_name="Ouverte par", on_delete=models.PROTECT, null=True, blank=True, related_name="nc_ouvertes")
    cloturee_par = models.ForeignKey(Utilisateur, verbose_name="Clôturée par", on_delete=models.PROTECT, null=True, blank=True, related_name="nc_cloturees")
    date_ouverture = models.DateTimeField("Ouverte le", auto_now_add=True)
    date_cloture = models.DateTimeField("Clôturée le", null=True, blank=True)

    class Meta:
        verbose_name = "Non-conformité"
        verbose_name_plural = "Non-conformités"
        ordering = ["-date_ouverture"]

    def __str__(self):
        return f"{self.numero} ({self.get_statut_display()})"

    TRANSITIONS = {
        StatutNC.OUVERTE: {StatutNC.EN_COURS, StatutNC.CLOTUREE},
        StatutNC.EN_COURS: {StatutNC.OUVERTE, StatutNC.CLOTUREE},
    }

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("NC")
        super().save(*args, **kwargs)

    def clean(self):
        ancien = valeur_en_base(self, "statut")
        if ancien == StatutNC.CLOTUREE:
            raise ValidationError(f"La non-conformité {self.numero} est clôturée : elle ne se modifie plus.")
        verifier_transition(ancien, self.statut, self.TRANSITIONS, "statut de la non-conformité", initial=StatutNC.OUVERTE)
        if not (self.description or "").strip():
            raise ValidationError({"description": "Décrivez la non-conformité."})
        if not (self.resultat_id or self.ordre_fabrication_id or self.lot_id or self.lot_matiere_id):
            raise ValidationError({"ordre_fabrication": "Une non-conformité se rattache à un contrôle, un OF ou un lot."})
        if self.statut == StatutNC.CLOTUREE and ancien != StatutNC.CLOTUREE and not getattr(self, "_cloture_verifiee", False):
            raise ValidationError({"statut": "La clôture se fait par l'action /cloturer/ (décision et vérifications)."})

    def verifier_suppression(self):
        raise ValidationError("Une non-conformité ne se supprime pas (historique qualité).")

    @classmethod
    def ouvrir_depuis(cls, resultat, utilisateur):
        """NC automatique sur un contrôle non conforme ; contrôle bloquant -> lot (PF ou matière) bloqué."""
        point = resultat.point
        valeur = f" : {resultat.valeur} {point.parametre.unite}" if resultat.valeur is not None else ""
        criteres = []
        if point.valeur_min is not None:
            criteres.append(f"min {point.valeur_min}")
        if point.valeur_max is not None:
            criteres.append(f"max {point.valeur_max}")
        if point.valeur_cible is not None:
            criteres.append(f"cible {point.valeur_cible}" + (f" ± {point.tolerance}" if point.tolerance is not None else ""))
        nc = cls.objects.create(
            resultat=resultat, ordre_fabrication=resultat.ordre_fabrication, lot=resultat.lot, lot_matiere=resultat.lot_matiere,
            description=f"{point.designation}{valeur} ({', '.join(criteres) or 'résultat observé non conforme'}).",
            bloquante=point.bloquant, ouverte_par=utilisateur,
            action_immediate=ActionImmediate.BLOCAGE_LOT if point.bloquant else ActionImmediate.ALERTE,
        )
        if point.bloquant:
            nc._bloquer_lots()
        from apps.core.notifications import notifier
        from apps.comptes.models import Profil
        profils = [Profil.RESPONSABLE_QUALITE] + ([Profil.RESPONSABLE_PRODUCTION] if resultat.ordre_fabrication_id else [])
        notifier(
            "Non-conformité qualité" + (" BLOQUANTE" if point.bloquant else ""),
            f"{nc.numero} - {nc.description}", document=nc, profils=profils,
        )
        return nc

    def _bloquer_lots(self):
        from apps.stocks.models import StatutLotMatiere
        if self.lot_id and self.lot.statut != StatutLot.BLOQUE:
            try:
                self.lot.bloquer(motif=self.numero)
            except ValueError:
                pass   # déjà vendu en partie : la NC reste ouverte et bloquante
        if self.lot_matiere_id and self.lot_matiere.statut in (StatutLotMatiere.A_CONTROLER, StatutLotMatiere.LIBERE):
            self.lot_matiere.changer_statut(StatutLotMatiere.BLOQUE)

    @transaction.atomic
    def cloturer(self, utilisateur, decision, action_corrective=""):
        """
        Clôture avec décision. Une NC bloquante issue d'un contrôle ne se
        clôture en LIBÉRATION que si un contrôle de reprise conforme existe.
        Lot matière : libération -> lot libéré ; rejet -> reste bloqué.
        """
        from django.utils import timezone
        from apps.stocks.models import StatutLotMatiere
        if self.statut == StatutNC.CLOTUREE:
            raise ValueError("Cette non-conformité est déjà clôturée.")
        if decision not in DecisionNC.values:
            raise ValueError("Décision attendue : " + ", ".join(DecisionNC.values) + ".")
        if action_corrective:
            self.action_corrective = action_corrective
        if not (self.action_corrective or "").strip():
            raise ValueError("Renseignez l'action corrective avant de clôturer.")
        if decision == DecisionNC.LIBERATION and self.bloquante and self.resultat_id and not self.resultat.reprises.filter(
            statut=StatutResultat.CONFORME,
        ).exists():
            raise ValueError("Libération refusée : aucun contrôle de reprise conforme n'a été enregistré.")
        self.decision = decision
        self.cloturee_par = utilisateur
        self.date_cloture = timezone.now()
        self.statut = StatutNC.CLOTUREE
        self._cloture_verifiee = True
        self.save()
        if self.lot_matiere_id and decision == DecisionNC.LIBERATION and self.lot_matiere.statut == StatutLotMatiere.BLOQUE:
            self.lot_matiere.changer_statut(StatutLotMatiere.LIBERE)
        return self


class PieceJointeQualite(models.Model):
    """Photos, bulletins d'analyse, documents fournisseur joints à un contrôle ou à une NC."""
    resultat = models.ForeignKey(ResultatControle, verbose_name="Contrôle", on_delete=models.PROTECT, null=True, blank=True, related_name="pieces_jointes")
    non_conformite = models.ForeignKey(NonConformite, verbose_name="Non-conformité", on_delete=models.PROTECT, null=True, blank=True, related_name="pieces_jointes")
    fichier = models.FileField("Fichier", upload_to="qualite/%Y/%m")
    description = models.CharField("Description", max_length=200, blank=True)
    ajoute_par = models.ForeignKey(Utilisateur, verbose_name="Ajouté par", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    date_ajout = models.DateTimeField("Ajouté le", auto_now_add=True)

    class Meta:
        verbose_name = "Pièce jointe qualité"
        verbose_name_plural = "Pièces jointes qualité"

    def clean(self):
        if not (self.resultat_id or self.non_conformite_id):
            raise ValidationError("Une pièce jointe se rattache à un contrôle ou à une non-conformité.")


# --- Génération et règles transverses ---------------------------------------

def points_applicables(of, declencheurs):
    """Contrôles actifs du plan qui concernent cet OF (activité, format, recette, étapes du circuit)."""
    from django.db.models import Q
    from django.utils import timezone
    aujourd_hui = timezone.localdate()
    activite = of.activite
    if activite is None:
        return PointControle.objects.none()
    points = PointControle.objects.filter(
        statut=StatutPointControle.ACTIF, declencheur__in=declencheurs, activite=activite,
    ).filter(
        Q(article__isnull=True) | Q(article_id=of.article_id),
        Q(fiche_technique__isnull=True) | Q(fiche_technique_id=of.fiche_technique_id),
        Q(date_debut__isnull=True) | Q(date_debut__lte=aujourd_hui),
        Q(date_fin__isnull=True) | Q(date_fin__gte=aujourd_hui),
    )
    if of.circuit_id:
        etapes = of.circuit.etapes.values_list("etape_id", flat=True)
        points = points.filter(Q(etape__isnull=True) | Q(etape_id__in=etapes))
    if of.ligne_id:
        points = points.filter(Q(poste__isnull=True) | Q(poste__ligne_id=of.ligne_id))
    return points


def generer_controles(of, declencheurs, lot=None):
    """
    Génère les contrôles à réaliser selon le plan (schéma qualité, étape 3) :
    au démarrage de l'OF (DEMARRAGE, CHAQUE_OF, premier PERIODIQUE), à
    chaque lot, à chaque changement de série. Pas de doublon pour les
    contrôles uniques par OF.
    """
    from django.utils import timezone
    crees = []
    for point in points_applicables(of, declencheurs):
        if point.declencheur in (Declencheur.DEMARRAGE, Declencheur.CHAQUE_OF, Declencheur.PERIODIQUE) and \
                ResultatControle.objects.filter(point=point, ordre_fabrication=of, est_reprise=False).exclude(statut=StatutResultat.ANNULE).exists():
            continue
        crees.append(ResultatControle.objects.create(
            point=point, ordre_fabrication=of, lot=lot if point.declencheur == Declencheur.CHAQUE_LOT else None,
            date_prevue=timezone.now(),
        ))
    return crees


def controle_reception_requis(article):
    return PointControle.objects.filter(
        statut=StatutPointControle.ACTIF, declencheur=Declencheur.RECEPTION, article=article,
    ).exists()


def generer_controles_reception(lot_matiere):
    from django.utils import timezone
    return [
        ResultatControle.objects.create(point=point, lot_matiere=lot_matiere, date_prevue=timezone.now())
        for point in PointControle.objects.filter(
            statut=StatutPointControle.ACTIF, declencheur=Declencheur.RECEPTION, article_id=lot_matiere.article_id,
        )
    ]


def _blocages(resultats, non_conformites):
    messages = []
    en_attente = resultats.filter(point__bloquant=True, statut__in=STATUTS_EN_ATTENTE)
    if en_attente.exists():
        messages.append(
            f"{en_attente.count()} contrôle(s) bloquant(s) non réalisé(s) ("
            + ", ".join(en_attente.values_list("numero", flat=True)[:5]) + ")"
        )
    ouvertes = non_conformites.filter(bloquante=True).exclude(statut=StatutNC.CLOTUREE)
    if ouvertes.exists():
        messages.append(
            f"{ouvertes.count()} non-conformité(s) bloquante(s) ouverte(s) ("
            + ", ".join(ouvertes.values_list("numero", flat=True)[:5]) + ")"
        )
    return messages


def blocages_qualite_of(of):
    """Ce qui empêche la clôture de l'OF (si le paramètre de production l'exige)."""
    from apps.production.models import ParametreProduction
    if not ParametreProduction.courant().controle_qualite_bloque_cloture:
        return []
    return _blocages(ResultatControle.objects.filter(ordre_fabrication=of), NonConformite.objects.filter(ordre_fabrication=of))


def blocages_qualite_lot(lot):
    """Ce qui empêche de déclarer le lot conforme / de le libérer."""
    from django.db.models import Q
    filtre_of = Q(lot=lot)
    if lot.ordre_fabrication_id:
        filtre_of |= Q(ordre_fabrication_id=lot.ordre_fabrication_id, lot__isnull=True)
    return _blocages(ResultatControle.objects.filter(filtre_of), NonConformite.objects.filter(filtre_of))
