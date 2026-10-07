"""
Socle industriel (Guide du paramétrage général, §3 à §12).

Référentiels créés une fois et utilisés par tous les modules :
- Activite : Eau, Jus, Yaourt (domaine industriel) ;
- Usine : site de production (distinct d'un dépôt extérieur) ;
- EtapeStandard : les étapes du circuit de référence (captage ->
  stockage produit fini), paramétrables ;
- Ligne / Poste / Equipement : trois objets distincts (§18) : la ligne
  dit OÙ l'on produit, le poste QUELLE fonction, l'équipement QUEL
  matériel physique (forage commun, cuves dédiées, machines...) ;
- Circuit / EtapeCircuit : l'ordre des opérations pour une activité,
  un produit/format et éventuellement une ligne. Versionné.

On paramètre ici des règles et des structures, jamais des quantités
(le stock et le réel restent des données opérationnelles).
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.comptes.models import Utilisateur
from apps.core import codification
from apps.core.models import generer_code_unique
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif_optionnel, exiger_pourcentage,
    valeur_en_base, verifier_transition,
)


def _code_depuis_libelle(modele, libelle, longueur=6, champ="code"):
    """EAU, JUS, YAOURT... : sigle du libellé, suffixé d'un chiffre si déjà pris."""
    base = codification.sigle(libelle, longueur)
    code, rang = base, 1
    while modele._default_manager.filter(**{champ: code}).exists():
        rang += 1
        code = f"{base}{rang}"
    return code


class Activite(ValidationAvantEnregistrement, models.Model):
    """Domaine industriel des produits, recettes, équipements et règles (Eau, Jus, Yaourt)."""
    code = models.CharField(
        "Code activité", max_length=20, unique=True, editable=False,
        help_text="Généré automatiquement depuis la désignation (EAU, JUS, YAOURT).",
    )
    designation = models.CharField("Désignation", max_length=100, unique=True)
    regles_specifiques = models.TextField("Règles spécifiques", blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Activité"
        verbose_name_plural = "Activités"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = _code_depuis_libelle(Activite, self.designation)
        super().save(*args, **kwargs)

    def clean(self):
        self.designation = (self.designation or "").strip()
        if not self.designation:
            raise ValidationError({"designation": "La désignation de l'activité est obligatoire."})


class Usine(ValidationAvantEnregistrement, models.Model):
    """
    Site physique de production (US-EAU, US-JY). Ne pas confondre avec un
    dépôt extérieur. Chaque usine peut désigner son magasin matières et
    son stock produits finis : les mouvements de ses OF y sont alors
    passés (sinon : « Magasin principal » / « Dépôt produits finis »).
    """
    code = models.CharField("Code usine", max_length=20, unique=True, editable=False)
    nom = models.CharField("Nom", max_length=100, unique=True)
    localisation = models.CharField("Adresse / localisation", max_length=255, blank=True)
    activites = models.ManyToManyField(Activite, verbose_name="Activités produites", blank=True, related_name="usines")
    magasin_matieres = models.ForeignKey(
        "stocks.Depot", verbose_name="Magasin matières de l'usine", on_delete=models.PROTECT,
        null=True, blank=True, related_name="usines_magasin",
    )
    stock_produits_finis = models.ForeignKey(
        "stocks.Depot", verbose_name="Stock produits finis de l'usine", on_delete=models.PROTECT,
        null=True, blank=True, related_name="usines_stock_pf",
    )
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Usine"
        verbose_name_plural = "Usines"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.nom}"

    def save(self, *args, **kwargs):
        if not self.code:
            mots = codification._ascii_majuscules(self.nom).replace("&", " ").split()
            utiles = [mot for mot in mots if mot not in {"USINE", "DE", "DU", "DES", "ET", "LA", "LE"}] or mots
            base = "US-" + "".join(mot[0] for mot in utiles) if len(utiles) > 1 else "US-" + codification.sigle(utiles[0])
            code, rang = base, 1
            while Usine.objects.filter(code=code).exists():
                rang += 1
                code = f"{base}{rang}"
            self.code = code
        super().save(*args, **kwargs)

    def clean(self):
        from apps.stocks.models import TypeLieu
        self.nom = (self.nom or "").strip()
        if not self.nom:
            raise ValidationError({"nom": "Le nom de l'usine est obligatoire."})
        if self.magasin_matieres_id and self.magasin_matieres.type_lieu not in (TypeLieu.MAGASIN_MATIERES, TypeLieu.STOCK_USINE):
            raise ValidationError({"magasin_matieres": "Le magasin matières doit être un lieu de type « Magasin matières » ou « Stock usine »."})
        if self.stock_produits_finis_id and self.stock_produits_finis.type_lieu != TypeLieu.STOCK_USINE:
            raise ValidationError({"stock_produits_finis": "Le stock produits finis doit être un lieu de type « Stock usine »."})


class PhaseEtape(models.TextChoices):
    AMONT = "AMONT", "Eau : captage, traitement, stockage process"
    PREPARATION = "PREPARATION", "Préparation du produit"
    CONDITIONNEMENT = "CONDITIONNEMENT", "Remplissage et conditionnement"
    APRES_PRODUCTION = "APRES_PRODUCTION", "Après production (hors coût de production)"


class EtapeStandard(ValidationAvantEnregistrement, models.Model):
    """
    Étape du circuit de référence (« Document — circuit complet de
    production ») : CAPTAGE, TRAITEMENT, STOCKAGE_PROCESS, PREPARATION,
    SOUFFLAGE, REMPLISSAGE... Liste paramétrable : on peut ajouter une
    étape (ex : FERMENTATION) sans redéploiement.
    """
    code = models.CharField("Code étape", max_length=30, unique=True)
    libelle = models.CharField("Libellé", max_length=100)
    phase = models.CharField("Phase", max_length=20, choices=PhaseEtape.choices, default=PhaseEtape.CONDITIONNEMENT)
    ordre_reference = models.PositiveIntegerField("Ordre dans le circuit de référence", default=0)
    sous_etape_de = models.ForeignKey(
        "self", verbose_name="Sous-étape de", on_delete=models.PROTECT, null=True, blank=True,
        related_name="sous_etapes",
        help_text="Ex : Décantation, Filtration, Cuve tampon et UV détaillent le Traitement de l'eau.",
    )
    description = models.TextField("Ce qui se passe à cette étape", blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Étape standard"
        verbose_name_plural = "Étapes standard"
        ordering = ["ordre_reference", "code"]

    def __str__(self):
        return f"{self.code} - {self.libelle}"

    @property
    def hors_cout_production(self):
        """Stockage produit fini et distribution ne font pas partie du coût de production."""
        return self.phase == PhaseEtape.APRES_PRODUCTION

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = "_".join(codification._ascii_majuscules(self.libelle).replace("/", " ").split())[:30]
        super().save(*args, **kwargs)

    def clean(self):
        if not (self.libelle or "").strip():
            raise ValidationError({"libelle": "Le libellé de l'étape est obligatoire."})
        ancien = valeur_en_base(self, "code")
        if ancien and ancien != self.code:
            raise ValidationError({"code": "Le code d'une étape ne change plus (il est utilisé par les OF, contrôles et coûts)."})
        if self.sous_etape_de_id and self.sous_etape_de_id == self.pk:
            raise ValidationError({"sous_etape_de": "Une étape ne peut pas être sa propre sous-étape."})


def _exiger_produits_finis(articles, champ):
    non_pf = [article.code for article in articles if article.type_article != "PRODUIT_FINI"]
    if non_pf:
        raise ValidationError({champ: "Seuls des produits finis (formats) sont attendus : " + ", ".join(non_pf) + "."})


class Ligne(ValidationAvantEnregistrement, models.Model):
    """Installation de production organisée : indique OÙ un produit peut être fabriqué (ne remplace pas le circuit)."""
    code = models.CharField("Code ligne", max_length=30, unique=True, editable=False)
    designation = models.CharField("Désignation", max_length=100)
    usine = models.ForeignKey(Usine, verbose_name="Usine", on_delete=models.PROTECT, related_name="lignes")
    activite = models.ForeignKey(Activite, verbose_name="Activité", on_delete=models.PROTECT, related_name="lignes")
    cadence_nominale = models.DecimalField("Capacité / cadence", max_digits=12, decimal_places=2, null=True, blank=True)
    unite_cadence = models.CharField("Unité de cadence", max_length=30, blank=True, help_text="Ex : bouteilles/heure.")
    formats_compatibles = models.ManyToManyField(
        "referentiel.Article", verbose_name="Formats compatibles", blank=True, related_name="lignes_compatibles",
        help_text="Vide = tous les formats de l'activité.",
    )
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Ligne de production"
        verbose_name_plural = "Lignes de production"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generer_code_unique(Ligne, f"LIG-{self.activite.code}", largeur=2)
        super().save(*args, **kwargs)

    def clean(self):
        exiger_positif_optionnel(self.cadence_nominale, "cadence_nominale", "La cadence", strict=True)
        if self.usine_id and self.activite_id and self.usine.activites.exists() \
                and not self.usine.activites.filter(pk=self.activite_id).exists():
            raise ValidationError({"activite": f"L'usine {self.usine.code} ne produit pas l'activité {self.activite.code}."})
        if self.pk and valeur_en_base(self, "activite") != self.activite_id:
            from apps.production.models import OrdreFabrication
            if OrdreFabrication.objects.filter(ligne_id=self.pk).exists():
                raise ValidationError({"activite": "Cette ligne a déjà des OF : son activité ne change plus."})

    def verifier_formats(self, formats):
        _exiger_produits_finis(formats, "formats_compatibles")
        hors_activite = [f.code for f in formats if f.activite_id and f.activite_id != self.activite_id]
        if hors_activite:
            raise ValidationError({"formats_compatibles": (
                f"Formats d'une autre activité que {self.activite.code} : " + ", ".join(hors_activite) + "."
            )})

    def accepte(self, article):
        """La ligne peut-elle produire ce format ?"""
        if article.activite_id and article.activite_id != self.activite_id:
            return False
        return not self.formats_compatibles.exists() or self.formats_compatibles.filter(pk=article.pk).exists()


class Poste(ValidationAvantEnregistrement, models.Model):
    """Opération / fonction de production au sein d'une ligne (le poste décrit la fonction, la machine l'équipement)."""
    code = models.CharField("Code poste", max_length=40, unique=True, editable=False)
    designation = models.CharField("Désignation", max_length=100, blank=True)
    ligne = models.ForeignKey(Ligne, verbose_name="Ligne", on_delete=models.PROTECT, related_name="postes")
    etape = models.ForeignKey(EtapeStandard, verbose_name="Fonction / étape", on_delete=models.PROTECT, related_name="postes")
    ordre = models.PositiveIntegerField("Ordre sur la ligne", default=0)
    formats_compatibles = models.ManyToManyField(
        "referentiel.Article", verbose_name="Formats compatibles", blank=True, related_name="postes_compatibles",
        help_text="Vide = les formats de la ligne.",
    )
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Poste"
        verbose_name_plural = "Postes"
        ordering = ["ligne", "ordre"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    def save(self, *args, **kwargs):
        if not self.designation and self.etape_id:
            self.designation = self.etape.libelle
        if not self.code:
            self.code = generer_code_unique(Poste, f"POST-{self.etape.code[:12]}", largeur=3)
        super().save(*args, **kwargs)

    def clean(self):
        if self.ligne_id and self.etape_id and Poste.objects.filter(
            ligne_id=self.ligne_id, etape_id=self.etape_id, ordre=self.ordre,
        ).exclude(pk=self.pk).exists():
            raise ValidationError({"ordre": "Ce poste existe déjà à cette position sur la ligne."})


class TypeEquipement(models.TextChoices):
    FORAGE = "FORAGE", "Forage / captage"
    POMPE = "POMPE", "Pompe"
    TRAITEMENT = "TRAITEMENT", "Traitement de l'eau (filtre, UV...)"
    CUVE = "CUVE", "Cuve"
    MELANGEUR = "MELANGEUR", "Mélangeur / cuve de préparation"
    PASTEURISATEUR = "PASTEURISATEUR", "Pasteurisateur / traitement thermique"
    SOUFFLEUSE = "SOUFFLEUSE", "Souffleuse"
    REMPLISSEUSE = "REMPLISSEUSE", "Remplisseuse"
    BOUCHEUSE = "BOUCHEUSE", "Boucheuse / operculeuse"
    ETIQUETEUSE = "ETIQUETEUSE", "Étiqueteuse"
    FARDELEUSE = "FARDELEUSE", "Fardeleuse / plastification"
    PALETTISEUR = "PALETTISEUR", "Palettiseur / filmeuse palette"
    LABORATOIRE = "LABORATOIRE", "Équipement de laboratoire"
    AUTRE = "AUTRE", "Autre"


class Equipement(ValidationAvantEnregistrement, models.Model):
    """
    Équipement physique (machine, forage, cuve...). Sans activité, il est
    COMMUN (ex : le forage, partagé par Eau, Jus et Yaourt : ses charges
    se répartissent entre activités) ; avec une activité, il est DÉDIÉ
    (ex : cuve Jus : ses charges vont directement à l'activité).
    """
    code = models.CharField("Code machine", max_length=30, unique=True, editable=False)
    designation = models.CharField("Désignation", max_length=100)
    type_equipement = models.CharField("Type", max_length=20, choices=TypeEquipement.choices)
    usine = models.ForeignKey(Usine, verbose_name="Usine", on_delete=models.PROTECT, related_name="equipements")
    poste = models.ForeignKey(Poste, verbose_name="Poste", on_delete=models.PROTECT, null=True, blank=True, related_name="equipements")
    activite = models.ForeignKey(
        Activite, verbose_name="Activité dédiée", on_delete=models.PROTECT, null=True, blank=True,
        related_name="equipements", help_text="Vide = équipement commun à plusieurs activités.",
    )
    cadence_nominale = models.DecimalField("Capacité / cadence", max_digits=12, decimal_places=2, null=True, blank=True)
    unite_cadence = models.CharField("Unité de cadence", max_length=30, blank=True)
    formats_compatibles = models.ManyToManyField(
        "referentiel.Article", verbose_name="Formats compatibles", blank=True, related_name="equipements_compatibles",
    )
    compteur_energie = models.BooleanField("Compteur d'énergie (kWh) disponible", default=False)
    compteur_heures = models.BooleanField("Compteur d'heures de marche disponible", default=False)
    compteur_pieces = models.BooleanField("Compteur de pièces disponible", default=False)
    compteur_volume = models.BooleanField("Débitmètre / compteur de volume disponible", default=False)
    valeur_acquisition = models.DecimalField("Valeur d'acquisition", max_digits=16, decimal_places=2, null=True, blank=True)
    duree_amortissement_mois = models.PositiveIntegerField("Durée d'amortissement (mois)", null=True, blank=True)
    date_mise_en_service = models.DateField("Date de mise en service", null=True, blank=True)
    actif = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Machine / équipement"
        verbose_name_plural = "Machines / équipements"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.designation}"

    @property
    def est_commun(self):
        return self.activite_id is None

    @property
    def amortissement_mensuel(self):
        if self.valeur_acquisition and self.duree_amortissement_mois:
            return self.valeur_acquisition / self.duree_amortissement_mois
        return None

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generer_code_unique(Equipement, f"M-{self.type_equipement[:5]}", largeur=2)
        super().save(*args, **kwargs)

    def clean(self):
        exiger_positif_optionnel(self.cadence_nominale, "cadence_nominale", "La cadence", strict=True)
        exiger_positif_optionnel(self.valeur_acquisition, "valeur_acquisition", "La valeur d'acquisition")
        if self.poste_id:
            ligne = self.poste.ligne
            if self.usine_id and ligne.usine_id != self.usine_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} est dans l'usine {ligne.usine.code}, pas dans {self.usine.code}."})
            if self.activite_id and ligne.activite_id != self.activite_id:
                raise ValidationError({"activite": f"Le poste {self.poste.code} appartient à une ligne {ligne.activite.code}."})
        if self.activite_id and self.usine_id and self.usine.activites.exists() \
                and not self.usine.activites.filter(pk=self.activite_id).exists():
            raise ValidationError({"activite": f"L'usine {self.usine.code} ne produit pas l'activité {self.activite.code}."})


class StatutCircuit(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    VALIDE = "VALIDE", "Validé"
    ARCHIVE = "ARCHIVE", "Remplacé / archivé"


class Circuit(ValidationAvantEnregistrement, models.Model):
    """
    Ordre des opérations pour fabriquer un produit (§12). Un circuit vaut
    pour une activité entière (article vide : « par famille lorsque la
    séquence est identique »), ou pour un format précis, et
    éventuellement pour une ligne. Versionné : Brouillon -> Validé ->
    Remplacé ; une seule version validée par (activité, format, ligne).
    """
    code = models.CharField("Code circuit", max_length=30, unique=True, editable=False)
    designation = models.CharField("Désignation", max_length=150)
    activite = models.ForeignKey(Activite, verbose_name="Activité", on_delete=models.PROTECT, related_name="circuits")
    article = models.ForeignKey(
        "referentiel.Article", verbose_name="Produit / format", on_delete=models.PROTECT,
        null=True, blank=True, related_name="circuits", help_text="Vide = tous les formats de l'activité.",
    )
    ligne = models.ForeignKey(Ligne, verbose_name="Ligne", on_delete=models.PROTECT, null=True, blank=True, related_name="circuits")
    version = models.PositiveIntegerField("Version", default=1)
    statut = models.CharField("Statut", max_length=20, choices=StatutCircuit.choices, default=StatutCircuit.BROUILLON)
    valide_par = models.ForeignKey(Utilisateur, verbose_name="Validé par", on_delete=models.PROTECT, null=True, blank=True, related_name="circuits_valides")
    date_validation = models.DateTimeField("Date de validation", null=True, blank=True)
    observations = models.TextField("Observations", blank=True)

    class Meta:
        verbose_name = "Circuit de production"
        verbose_name_plural = "Circuits de production"
        ordering = ["activite", "code", "-version"]

    def __str__(self):
        return f"{self.code} v{self.version} - {self.designation}"

    TRANSITIONS = {
        StatutCircuit.BROUILLON: {StatutCircuit.VALIDE},
        StatutCircuit.VALIDE: {StatutCircuit.ARCHIVE},
    }

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generer_code_unique(Circuit, f"CIR-{self.activite.code}", largeur=3)
        super().save(*args, **kwargs)

    def clean(self):
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutCircuit.ARCHIVE:
            raise ValidationError("Ce circuit est archivé : il ne peut plus être modifié.")
        verifier_transition(ancien_statut, self.statut, self.TRANSITIONS, "statut du circuit", initial=StatutCircuit.BROUILLON)
        if ancien_statut == StatutCircuit.VALIDE:
            for champ in ("activite", "article", "ligne"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Un circuit validé ne se modifie plus : créez une nouvelle version."})
        if self.article_id:
            _exiger_produits_finis([self.article], "article")
            if self.article.activite_id and self.activite_id and self.article.activite_id != self.activite_id:
                raise ValidationError({"article": f"{self.article.code} n'appartient pas à l'activité {self.activite.code}."})
        if self.ligne_id and self.activite_id and self.ligne.activite_id != self.activite_id:
            raise ValidationError({"ligne": f"La ligne {self.ligne.code} est une ligne {self.ligne.activite.code}."})
        if self.ligne_id and self.article_id and not self.ligne.accepte(self.article):
            raise ValidationError({"ligne": f"La ligne {self.ligne.code} n'est pas compatible avec {self.article.code}."})

    def verifier_suppression(self):
        if self.statut != StatutCircuit.BROUILLON:
            raise ValidationError("Seul un circuit en brouillon peut être supprimé (historique des versions).")

    @transaction.atomic
    def valider(self, utilisateur):
        """Brouillon -> Validé ; la version validée précédente du même périmètre est archivée."""
        from django.utils import timezone
        if self.statut != StatutCircuit.BROUILLON:
            raise ValueError("Seul un circuit en brouillon peut être validé.")
        if not self.etapes.exists():
            raise ValueError("Impossible de valider un circuit sans étape.")
        for ancien in Circuit.objects.filter(
            activite_id=self.activite_id, article_id=self.article_id, ligne_id=self.ligne_id, statut=StatutCircuit.VALIDE,
        ).exclude(pk=self.pk):
            ancien.statut = StatutCircuit.ARCHIVE
            ancien.save()
        self.statut = StatutCircuit.VALIDE
        self.valide_par = utilisateur
        self.date_validation = timezone.now()
        self.save()

    @transaction.atomic
    def nouvelle_version(self, utilisateur=None):
        """Copie le circuit (et ses étapes) en une nouvelle version brouillon."""
        meme_perimetre = Circuit.objects.filter(
            activite_id=self.activite_id, article_id=self.article_id, ligne_id=self.ligne_id,
        )
        version = (meme_perimetre.aggregate(m=models.Max("version"))["m"] or self.version) + 1
        copie = Circuit.objects.create(
            designation=self.designation, activite=self.activite, article=self.article, ligne=self.ligne,
            version=version, observations=self.observations,
        )
        for etape in self.etapes.all():
            EtapeCircuit.objects.create(
                circuit=copie, etape=etape.etape, ordre=etape.ordre, obligatoire=etape.obligatoire,
                poste=etape.poste, equipement=etape.equipement, temps_theorique_min=etape.temps_theorique_min,
                perte_theorique_pct=etape.perte_theorique_pct,
            )
        return copie


def circuit_pour(article, ligne=None):
    """
    Circuit validé à appliquer à un OF : le plus précis l'emporte
    (format + ligne > format > activité + ligne > activité). None si
    l'activité n'a pas encore de circuit validé.
    """
    if article is None or not article.activite_id:
        return None
    candidats = Circuit.objects.filter(statut=StatutCircuit.VALIDE, activite_id=article.activite_id)
    ligne_id = ligne.pk if ligne else None
    for filtre in (
        {"article_id": article.pk, "ligne_id": ligne_id},
        {"article_id": article.pk, "ligne__isnull": True},
        {"article__isnull": True, "ligne_id": ligne_id},
        {"article__isnull": True, "ligne__isnull": True},
    ):
        if "ligne_id" in filtre and ligne_id is None:
            continue
        circuit = candidats.filter(**filtre).order_by("-version").first()
        if circuit:
            return circuit
    return None


class EtapeCircuit(ValidationAvantEnregistrement, models.Model):
    """Une étape d'un circuit, dans l'ordre, avec poste/machine et valeurs théoriques si connues."""
    circuit = models.ForeignKey(Circuit, verbose_name="Circuit", on_delete=models.CASCADE, related_name="etapes")
    etape = models.ForeignKey(EtapeStandard, verbose_name="Étape", on_delete=models.PROTECT, related_name="utilisations")
    ordre = models.PositiveIntegerField("Ordre")
    obligatoire = models.BooleanField(
        "Obligatoire", default=True,
        help_text="Ex : le soufflage n'existe que si la bouteille est soufflée sur site.",
    )
    poste = models.ForeignKey(Poste, verbose_name="Poste", on_delete=models.PROTECT, null=True, blank=True)
    equipement = models.ForeignKey(Equipement, verbose_name="Machine", on_delete=models.PROTECT, null=True, blank=True)
    temps_theorique_min = models.DecimalField("Temps théorique (min)", max_digits=10, decimal_places=2, null=True, blank=True)
    perte_theorique_pct = models.DecimalField("Perte théorique (%)", max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "Étape de circuit"
        verbose_name_plural = "Étapes de circuit"
        ordering = ["circuit", "ordre"]
        unique_together = [("circuit", "etape"), ("circuit", "ordre")]

    def __str__(self):
        return f"{self.circuit.code} #{self.ordre} {self.etape.libelle}"

    def clean(self):
        exiger_positif_optionnel(self.temps_theorique_min, "temps_theorique_min", "Le temps théorique")
        exiger_pourcentage(self.perte_theorique_pct, "perte_theorique_pct", "La perte théorique")
        circuit_id = valeur_en_base(self, "circuit") or self.circuit_id
        circuit = Circuit.objects.filter(pk=circuit_id).first() or (self.circuit if self.circuit_id else None)
        if circuit and circuit.pk and circuit.statut != StatutCircuit.BROUILLON:
            raise ValidationError("Ce circuit n'est plus en brouillon : ses étapes sont figées (créez une nouvelle version).")
        if self.circuit_id and self.etape_id and EtapeCircuit.objects.filter(
            circuit_id=self.circuit_id, etape_id=self.etape_id,
        ).exclude(pk=self.pk).exists():
            raise ValidationError({"etape": f"L'étape {self.etape.libelle} figure déjà dans ce circuit."})
        if self.circuit_id and EtapeCircuit.objects.filter(circuit_id=self.circuit_id, ordre=self.ordre).exclude(pk=self.pk).exists():
            raise ValidationError({"ordre": f"La position {self.ordre} est déjà occupée dans ce circuit."})
        if self.poste_id:
            if self.etape_id and self.poste.etape_id != self.etape_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} réalise l'étape {self.poste.etape.libelle}, pas {self.etape.libelle}."})
            if self.circuit_id and self.circuit.ligne_id and self.poste.ligne_id != self.circuit.ligne_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} n'est pas sur la ligne du circuit."})
            if self.circuit_id and self.poste.ligne.activite_id != self.circuit.activite_id:
                raise ValidationError({"poste": f"Le poste {self.poste.code} est sur une ligne d'une autre activité."})
        if self.equipement_id:
            if self.poste_id and self.equipement.poste_id and self.equipement.poste_id != self.poste_id:
                raise ValidationError({"equipement": f"La machine {self.equipement.code} n'est pas affectée à ce poste."})
            if self.circuit_id and self.equipement.activite_id and self.equipement.activite_id != self.circuit.activite_id:
                raise ValidationError({"equipement": f"La machine {self.equipement.code} est dédiée à une autre activité."})

    def verifier_suppression(self):
        if self.circuit.statut != StatutCircuit.BROUILLON:
            raise ValidationError("Ce circuit n'est plus en brouillon : ses étapes sont figées.")
