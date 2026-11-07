"""
Module 3 - Achats et approvisionnements.

Couvre tous les onglets prévus au §6.1 du cahier des charges :
besoins d'approvisionnement, demandes d'achat, commandes fournisseurs,
fournisseurs, réceptions, contrôle réception, retours fournisseurs.

Piloté par le profil RESPONSABLE_ACHATS (ajouté car le cahier des
charges décrit ce module en détail sans jamais nommer explicitement
qui le pilote - voir échange avec le client à ce sujet). Le
Responsable Achat gère :
- les fournisseurs et leurs contrats (ContratFournisseur)
- le catalogue des produits que chaque fournisseur peut livrer, avec
  son prix (ArticleFournisseur)
- les commandes fournisseurs et leur suivi jusqu'à réception
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from apps.comptes.models import Utilisateur
from apps.referentiel.models import Article
from apps.core.models import generer_numero, generer_code_unique
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, exiger_ordre_dates,
    valeur_en_base, verifier_transition,
)


class Fournisseur(models.Model):
    """Un fournisseur de matières premières, emballages ou services."""
    code = models.CharField(
        "Code fournisseur", max_length=30, unique=True, editable=False,
        help_text="Généré automatiquement (FRS-000001...), jamais saisi.",
    )
    nom = models.CharField("Nom", max_length=150)
    contact = models.CharField("Contact", max_length=150, blank=True)
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    email = models.EmailField("Email", blank=True)
    adresse = models.CharField("Adresse", max_length=255, blank=True)
    ifu = models.CharField("IFU", max_length=30, blank=True)
    gere_par = models.ForeignKey(
        Utilisateur, verbose_name="Géré par (Responsable Achat)",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fournisseurs_geres",
    )
    actif = models.BooleanField("Actif", default=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Fournisseur"
        verbose_name_plural = "Fournisseurs"
        ordering = ["nom"]

    def __str__(self):
        return f"{self.code} - {self.nom}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = generer_code_unique(Fournisseur, "FRS")
        super().save(*args, **kwargs)


class StatutContratFournisseur(models.TextChoices):
    ACTIF = "ACTIF", "Actif"
    EXPIRE = "EXPIRE", "Expiré"
    RESILIE = "RESILIE", "Résilié"
    BROUILLON = "BROUILLON", "Brouillon"


class ContratFournisseur(ValidationAvantEnregistrement, models.Model):
    """
    Le contrat qui lie EVAM à un fournisseur : conditions générales,
    durée, éventuellement des prix ou délais négociés qui s'appliquent
    par défaut aux ArticleFournisseur de ce fournisseur.
    Géré exclusivement par le Responsable Achat.
    """
    numero = models.CharField("Numéro de contrat", max_length=30, unique=True, editable=False)
    fournisseur = models.ForeignKey(
        Fournisseur, verbose_name="Fournisseur", on_delete=models.CASCADE,
        related_name="contrats",
    )
    date_debut = models.DateField("Date de début")
    date_fin = models.DateField("Date de fin", null=True, blank=True)
    conditions = models.TextField(
        "Conditions particulières", blank=True,
        help_text="Modalités de paiement, délais de livraison garantis, pénalités, exclusivité...",
    )
    statut = models.CharField(
        "Statut", max_length=15, choices=StatutContratFournisseur.choices,
        default=StatutContratFournisseur.BROUILLON,
    )
    gere_par = models.ForeignKey(
        Utilisateur, verbose_name="Négocié par (Responsable Achat)",
        on_delete=models.PROTECT, related_name="contrats_fournisseurs_geres",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Contrat fournisseur"
        verbose_name_plural = "Contrats fournisseurs"
        ordering = ["-date_debut"]

    def __str__(self):
        return f"{self.numero} - {self.fournisseur.nom} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("CTF")
        super().save(*args, **kwargs)

    def clean(self):
        exiger_ordre_dates(self.date_debut, self.date_fin, "date_fin", "la date de début", "La date de fin")


class ArticleFournisseur(ValidationAvantEnregistrement, models.Model):
    """
    Le catalogue : quel fournisseur peut livrer quel article, à quel
    prix et sous quel délai. C'est cette table que le Responsable
    Achat consulte pour choisir un fournisseur au moment de créer une
    commande ("achats des produits fournis par les fournisseurs").
    """
    fournisseur = models.ForeignKey(
        Fournisseur, verbose_name="Fournisseur", on_delete=models.CASCADE,
        related_name="articles_fournis",
    )
    article = models.ForeignKey(
        Article, verbose_name="Article fourni", on_delete=models.CASCADE,
        related_name="fournisseurs_disponibles",
    )
    contrat = models.ForeignKey(
        ContratFournisseur, verbose_name="Contrat associé", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="articles_couverts",
    )
    prix_unitaire = models.DecimalField("Prix unitaire négocié", max_digits=14, decimal_places=2)
    delai_livraison_jours = models.PositiveIntegerField("Délai de livraison (jours)", null=True, blank=True)
    reference_fournisseur = models.CharField("Référence chez le fournisseur", max_length=100, blank=True)

    class Meta:
        verbose_name = "Article fourni par un fournisseur"
        verbose_name_plural = "Catalogue des articles fournisseurs"
        unique_together = ("fournisseur", "article")

    def __str__(self):
        return f"{self.article.code} chez {self.fournisseur.nom} : {self.prix_unitaire}"

    def clean(self):
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire négocié")
        if self.contrat_id and self.fournisseur_id and self.contrat.fournisseur_id != self.fournisseur_id:
            raise ValidationError({"contrat": "Ce contrat appartient à un autre fournisseur."})


class OrigineBesoin(models.TextChoices):
    AUTO_PRODUCTION = "AUTO_PRODUCTION", "Généré automatiquement par la production"
    SEUIL_ALERTE = "SEUIL_ALERTE", "Stock passé sous le seuil d'alerte"
    MANUEL = "MANUEL", "Saisi manuellement"


# Types d'articles achetés (les produits fabriqués ne génèrent pas de besoin d'achat).
TYPES_ARTICLES_ACHETES = ("MATIERE_PREMIERE", "EMBALLAGE", "CONSOMMABLE")
ORIGINES_AUTOMATIQUES = (OrigineBesoin.AUTO_PRODUCTION, OrigineBesoin.SEUIL_ALERTE)


def besoins_production(article):
    """
    Quantité de l'article encore attendue par les OF non terminés, et ces OF.
    - OF en brouillon : tout son besoin théorique (rien n'est encore réservé) ;
    - OF lancé : seulement la part qui n'a pas pu être réservée au lancement
      et n'a pas été sortie depuis (le reste est déjà compté dans le stock
      réservé, donc retiré du disponible).
    """
    from decimal import Decimal
    from django.db.models import Sum
    from apps.production.models import BesoinMatierePrevu, ReservationMatiere, SortieMatiere, StatutOF
    statuts_ouverts = (
        StatutOF.BROUILLON, StatutOF.A_PREPARER, StatutOF.MATIERES_EN_PREPARATION, StatutOF.PRET, StatutOF.EN_PRODUCTION,
    )
    total, ofs = Decimal("0"), []
    for besoin_of in BesoinMatierePrevu.objects.filter(
        matiere=article, ordre_fabrication__statut__in=statuts_ouverts,
    ).select_related("ordre_fabrication"):
        of = besoin_of.ordre_fabrication
        attendu = Decimal(besoin_of.quantite_theorique)
        if of.statut != StatutOF.BROUILLON:
            reservation = ReservationMatiere.objects.filter(ordre_fabrication=of, matiere=article).aggregate(
                reservee=Sum("quantite_reservee"), restante=Sum("quantite_restante"),
            )
            reservee = reservation["reservee"] or Decimal("0")
            consommee = reservee - (reservation["restante"] or Decimal("0"))
            sorties = SortieMatiere.objects.filter(ordre_fabrication=of, matiere=article).aggregate(
                total=Sum("quantite_sortie"),
            )["total"] or Decimal("0")
            attendu -= reservee + max(sorties - consommee, Decimal("0"))
        if attendu > 0:
            total += attendu
            ofs.append(of)
    return total, ofs


def quantite_en_cours_achat(article):
    """
    Ce qui est déjà en route pour l'article, en unité de stock : demandes
    d'achat en attente ou approuvées, et reste à recevoir des commandes
    fournisseurs non soldées (brouillon, envoyée, partiellement reçue).
    Une demande transformée est comptée via sa commande.
    """
    from decimal import Decimal
    from django.db.models import Sum
    demandes = DemandeAchat.objects.filter(
        article=article, statut__in=(StatutDemandeAchat.EN_ATTENTE, StatutDemandeAchat.APPROUVEE),
    ).aggregate(total=Sum("quantite_demandee"))["total"] or Decimal("0")
    commandes = sum(
        (ligne.en_unite_de_stock(ligne.reste_a_recevoir) for ligne in LigneCommandeFournisseur.objects.filter(
            article=article, commande__statut__in=(
                StatutCommandeFournisseur.BROUILLON, StatutCommandeFournisseur.ENVOYEE,
                StatutCommandeFournisseur.PARTIELLEMENT_RECUE,
            ),
        ).select_related("article") if ligne.reste_a_recevoir > 0),
        Decimal("0"),
    )
    return demandes + commandes


def recalculer_besoin_article(article):
    """
    UN SEUL besoin d'achat automatique ouvert par matière (§6.2), qui
    couvre à la fois les OF et le seuil d'alerte :

        manque = besoins des OF non terminés + seuil d'alerte
                 - stock disponible (tous dépôts)
                 - quantités déjà en cours d'achat (demandes, commandes)
                 - besoins saisis à la main encore ouverts

    - manque > 0 : le besoin ouvert est créé (Responsable Achat notifié)
      ou mis à jour ; origine « production » si des OF en ont besoin,
      sinon « seuil d'alerte » ; il est rattaché aux OF concernés ;
    - manque <= 0 : le besoin ouvert est soldé.
    Un besoin transformé en demande d'achat n'est plus touché : sa demande
    est alors comptée « en cours », ce qui évite de commander deux fois.

    Appelé après chaque mouvement de stock (apps/stocks/signals.py), à
    chaque changement d'un OF, d'une demande ou d'une commande.
    """
    from decimal import Decimal, ROUND_UP
    from django.db.models import F as Champ, Sum
    from apps.stocks.models import StockArticle
    if article.type_article not in TYPES_ARTICLES_ACHETES:
        return
    production, ofs = besoins_production(article)
    alerte = Decimal(article.stock_alerte or 0)
    ouverts = list(BesoinApprovisionnement.objects.filter(
        article=article, origine__in=ORIGINES_AUTOMATIQUES, satisfait=False,
    ).order_by("pk"))
    besoin = ouverts[0] if ouverts else None
    for doublon in ouverts[1:]:                       # ne laisser qu'un besoin ouvert
        doublon.satisfait = True
        doublon.save()
    if production <= 0 and alerte <= 0:
        manque = Decimal("0")
    else:
        disponible = StockArticle.objects.filter(article=article).aggregate(
            total=Sum(Champ("quantite_physique") - Champ("quantite_bloquee") - Champ("quantite_reservee")),
        )["total"] or Decimal("0")
        manuels = BesoinApprovisionnement.objects.filter(
            article=article, origine=OrigineBesoin.MANUEL, satisfait=False,
        ).aggregate(total=Sum("quantite_besoin"))["total"] or Decimal("0")
        manque = production + alerte - disponible - quantite_en_cours_achat(article) - manuels
        manque = manque.quantize(Decimal("0.001"), rounding=ROUND_UP)
    if manque <= 0:
        if besoin is not None:
            besoin.satisfait = True
            besoin.save()
        return
    origine = OrigineBesoin.AUTO_PRODUCTION if production > 0 else OrigineBesoin.SEUIL_ALERTE
    if besoin is None:
        besoin = BesoinApprovisionnement.objects.create(article=article, quantite_besoin=manque, origine=origine)
        besoin.ordres_fabrication.set(ofs)
        from apps.core.notifications import notifier
        from apps.comptes.models import Profil
        cause = (f"pour {', '.join(of.numero for of in ofs)}" if ofs else "stock sous le seuil d'alerte")
        notifier(
            "Besoin d'achat à traiter",
            f"{article.code} - {article.designation} : manque {manque} ({cause})",
            document=besoin, profils=[Profil.RESPONSABLE_ACHATS],
        )
        return
    if (besoin.quantite_besoin, besoin.origine) != (manque, origine):
        besoin.quantite_besoin, besoin.origine = manque, origine
        besoin.save()
    besoin.ordres_fabrication.set(ofs)


def verifier_seuil_alerte(article):
    """Après un mouvement de stock (apps/stocks/signals.py) : voir recalculer_besoin_article."""
    recalculer_besoin_article(article)


def recalculer_besoins_articles(articles):
    """Recalcule le besoin de chaque article (sans doublon)."""
    vus = set()
    for article in articles:
        if article is not None and article.pk not in vus:
            vus.add(article.pk)
            recalculer_besoin_article(article)


def synchroniser_besoins_of(of):
    """
    Après un changement de l'OF (création, quantité, statut, annulation,
    libération des réservations) : recalcul des matières de l'OF, et de
    celles qu'il ne demande plus (besoins encore ouverts qui lui sont liés).
    """
    articles = [b.matiere for b in of.besoins_matieres.select_related("matiere")]
    articles += [b.article for b in BesoinApprovisionnement.objects.filter(
        ordres_fabrication=of, satisfait=False,
    ).select_related("article")]
    recalculer_besoins_articles(articles)


class BesoinApprovisionnement(ValidationAvantEnregistrement, models.Model):
    """
    Un besoin d'achat. Le cahier des charges (§6.2) précise que ce
    besoin peut être généré automatiquement quand un stock passe sous
    un seuil suite à un OF, ou saisi manuellement par le service achats.
    """
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    quantite_besoin = models.DecimalField("Quantité nécessaire", max_digits=14, decimal_places=3)
    origine = models.CharField("Origine du besoin", max_length=20, choices=OrigineBesoin.choices)
    satisfait = models.BooleanField("Satisfait par une commande", default=False)
    ordres_fabrication = models.ManyToManyField(
        "production.OrdreFabrication", verbose_name="OF à l'origine du besoin",
        blank=True, related_name="besoins_achat",
        help_text="OF dont les matières manquantes sont couvertes par ce besoin (besoin généré par la production).",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Besoin d'approvisionnement"
        verbose_name_plural = "Besoins d'approvisionnement"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Besoin {self.quantite_besoin} {self.article.code}"

    def clean(self):
        exiger_positif(self.quantite_besoin, "quantite_besoin", "La quantité nécessaire")

    @transaction.atomic
    def creer_demande_achat(self, demandeur):
        """
        Bouton « Créer une DA » de l'écran Besoins d'achat : la demande
        reprend l'article et la quantité du besoin (rien à ressaisir) ;
        le besoin est alors considéré comme pris en charge.
        """
        if self.satisfait:
            raise ValueError("Ce besoin est déjà pris en charge.")
        if self.demandes_achat.exclude(statut=StatutDemandeAchat.REJETEE).exists():
            raise ValueError("Une demande d'achat est déjà en cours pour ce besoin.")
        demande = DemandeAchat.objects.create(
            besoin=self, article=self.article, quantite_demandee=self.quantite_besoin,
            motif=f"{self.get_origine_display()} ({self.article.code})", demandeur=demandeur,
        )
        self.satisfait = True
        self.save()
        recalculer_besoin_article(self.article)
        return demande


class StatutDemandeAchat(models.TextChoices):
    """Onglet "demandes d'achat" du §6.1 - distinct de la commande :
    une demande interne à valider avant de devenir une commande fournisseur."""
    EN_ATTENTE = "EN_ATTENTE", "En attente"
    APPROUVEE = "APPROUVEE", "Approuvée"
    REJETEE = "REJETEE", "Rejetée"
    TRANSFORMEE = "TRANSFORMEE", "Transformée en commande"


class DemandeAchat(ValidationAvantEnregistrement, models.Model):
    """
    Une demande d'achat interne (ex : émise par le Responsable
    Production ou issue d'un BesoinApprovisionnement), que le
    Responsable Achat approuve avant de créer la commande fournisseur
    correspondante.
    """
    besoin = models.ForeignKey(
        BesoinApprovisionnement, verbose_name="Besoin d'origine",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="demandes_achat",
    )
    article = models.ForeignKey(Article, verbose_name="Article demandé", on_delete=models.PROTECT)
    quantite_demandee = models.DecimalField("Quantité demandée", max_digits=14, decimal_places=3)
    motif = models.TextField("Motif", blank=True)
    demandeur = models.ForeignKey(
        Utilisateur, verbose_name="Demandeur", on_delete=models.PROTECT,
        related_name="demandes_achat_emises",
    )
    statut = models.CharField(
        "Statut", max_length=15, choices=StatutDemandeAchat.choices,
        default=StatutDemandeAchat.EN_ATTENTE,
    )
    approuve_par = models.ForeignKey(
        Utilisateur, verbose_name="Approuvée par (Responsable Achat)",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="demandes_achat_approuvees",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    date_traitement = models.DateTimeField("Date de traitement", null=True, blank=True)

    class Meta:
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"
        ordering = ["-date_creation"]

    def __str__(self):
        return f"Demande {self.quantite_demandee} {self.article.code} ({self.get_statut_display()})"

    TRANSITIONS = {
        StatutDemandeAchat.EN_ATTENTE: {StatutDemandeAchat.APPROUVEE, StatutDemandeAchat.REJETEE},
        StatutDemandeAchat.APPROUVEE: {StatutDemandeAchat.TRANSFORMEE},
    }

    def clean(self):
        exiger_positif(self.quantite_demandee, "quantite_demandee", "La quantité demandée")
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutDemandeAchat.REJETEE, StatutDemandeAchat.TRANSFORMEE):
            raise ValidationError(
                f"Cette demande est {dict(StatutDemandeAchat.choices)[ancien_statut].lower()} : elle ne peut plus être modifiée."
            )
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de la demande",
            initial=StatutDemandeAchat.EN_ATTENTE,
        )
        if ancien_statut == StatutDemandeAchat.APPROUVEE:
            for champ in ("article",):
                if valeur_en_base(self, champ) != self.article_id:
                    raise ValidationError({champ: "Une demande approuvée ne peut plus changer d'article."})
            if valeur_en_base(self, "quantite_demandee") != self.quantite_demandee:
                raise ValidationError({"quantite_demandee": "Une demande approuvée ne peut plus changer de quantité."})

    def verifier_suppression(self):
        if self.statut != StatutDemandeAchat.EN_ATTENTE:
            raise ValidationError("Seule une demande en attente peut être supprimée.")

    def save(self, *args, **kwargs):
        creation = self._state.adding
        super().save(*args, **kwargs)
        # Demande saisie directement (hors besoin) : elle couvre une partie du
        # besoin automatique ouvert. Celle créée depuis un besoin est recalculée
        # par creer_demande_achat, une fois le besoin pris en charge.
        if creation and not self.besoin_id:
            recalculer_besoin_article(self.article)

    def delete(self, *args, **kwargs):
        article = self.article
        resultat = super().delete(*args, **kwargs)
        recalculer_besoin_article(article)
        return resultat

    def _verifier_en_attente(self):
        if self.statut != StatutDemandeAchat.EN_ATTENTE:
            raise ValueError(f"Cette demande est déjà {self.get_statut_display().lower()}.")

    def approuver(self, utilisateur):
        from django.utils import timezone
        self._verifier_en_attente()
        self.statut = StatutDemandeAchat.APPROUVEE
        self.approuve_par = utilisateur
        self.date_traitement = timezone.now()
        self.save()

    def rejeter(self, utilisateur):
        from django.utils import timezone
        self._verifier_en_attente()
        self.statut = StatutDemandeAchat.REJETEE
        self.approuve_par = utilisateur
        self.date_traitement = timezone.now()
        self.save()
        # Demande rejetée : le besoin d'origine redevient à traiter (et sa
        # quantité est recalculée ; un seul besoin ouvert par matière).
        if self.besoin_id and self.besoin.satisfait and self.besoin.origine in ORIGINES_AUTOMATIQUES:
            BesoinApprovisionnement.objects.filter(
                article_id=self.article_id, origine__in=ORIGINES_AUTOMATIQUES, satisfait=False,
            ).exclude(pk=self.besoin_id).update(satisfait=True)
        if self.besoin_id and self.besoin.satisfait:
            self.besoin.satisfait = False
            self.besoin.save()
        recalculer_besoin_article(self.article)


class StatutCommandeFournisseur(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    ENVOYEE = "ENVOYEE", "Envoyée"
    PARTIELLEMENT_RECUE = "PARTIELLEMENT_RECUE", "Partiellement reçue"
    RECUE = "RECUE", "Reçue"
    ANNULEE = "ANNULEE", "Annulée"


class CommandeFournisseur(ValidationAvantEnregistrement, models.Model):
    """La commande passée par le Responsable Achat à un fournisseur."""
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    fournisseur = models.ForeignKey(Fournisseur, verbose_name="Fournisseur", on_delete=models.PROTECT, related_name="commandes")
    demande_achat = models.ForeignKey(
        DemandeAchat, verbose_name="Demande d'achat d'origine",
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="commandes",
    )
    statut = models.CharField(
        "Statut", max_length=25, choices=StatutCommandeFournisseur.choices,
        default=StatutCommandeFournisseur.BROUILLON,
    )
    cree_par = models.ForeignKey(
        Utilisateur, verbose_name="Créée par (Responsable Achat)",
        on_delete=models.PROTECT, related_name="commandes_fournisseurs_creees",
    )
    date_commande = models.DateTimeField("Date de commande", auto_now_add=True)

    class Meta:
        verbose_name = "Commande fournisseur"
        verbose_name_plural = "Commandes fournisseurs"
        ordering = ["-date_commande"]

    def __str__(self):
        return f"{self.numero} - {self.fournisseur.nom}"

    TRANSITIONS = {
        StatutCommandeFournisseur.BROUILLON: {StatutCommandeFournisseur.ENVOYEE, StatutCommandeFournisseur.ANNULEE},
        StatutCommandeFournisseur.ENVOYEE: {
            StatutCommandeFournisseur.PARTIELLEMENT_RECUE, StatutCommandeFournisseur.RECUE,
            StatutCommandeFournisseur.ANNULEE,
        },
        StatutCommandeFournisseur.PARTIELLEMENT_RECUE: {StatutCommandeFournisseur.RECUE},
    }

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.numero:
                self.numero = generer_numero("CMF")
            nouvelle = self._state.adding
            super().save(*args, **kwargs)
            # La demande d'achat approuvée devient "Transformée en commande".
            if nouvelle and self.demande_achat_id:
                self.demande_achat.statut = StatutDemandeAchat.TRANSFORMEE
                self.demande_achat.save()
            # Commande annulée : ce qu'elle devait livrer redevient à acheter.
            if self.statut == StatutCommandeFournisseur.ANNULEE and not nouvelle:
                recalculer_besoins_articles(l.article for l in self.lignes.select_related("article"))

    def delete(self, *args, **kwargs):
        articles = [l.article for l in self.lignes.select_related("article")]
        resultat = super().delete(*args, **kwargs)
        recalculer_besoins_articles(articles)
        return resultat

    def clean(self):
        """
        - fournisseur actif, demande d'achat d'origine approuvée ;
        - statut : Brouillon -> Envoyée -> (Partiellement) reçue, ou
          Annulée tant que rien n'a été reçu ; Reçue/Annulée sont figées ;
        - fournisseur et demande ne changent plus après le brouillon.
        """
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutCommandeFournisseur.RECUE, StatutCommandeFournisseur.ANNULEE):
            raise ValidationError(
                f"La commande {self.numero} est {dict(StatutCommandeFournisseur.choices)[ancien_statut].lower()} : "
                "elle ne peut plus être modifiée."
            )
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut de la commande fournisseur",
            initial=StatutCommandeFournisseur.BROUILLON,
        )
        if self.statut == StatutCommandeFournisseur.ANNULEE and self.pk and self.receptions.exists():
            raise ValidationError({"statut": "Cette commande a déjà des réceptions : elle ne peut plus être annulée."})
        if ancien_statut is None:
            if self.fournisseur_id and not self.fournisseur.actif:
                raise ValidationError({"fournisseur": f"Le fournisseur « {self.fournisseur.nom} » est inactif."})
            if self.demande_achat_id and self.demande_achat.statut != StatutDemandeAchat.APPROUVEE:
                raise ValidationError({"demande_achat": (
                    f"La demande d'achat est {self.demande_achat.get_statut_display().lower()} : "
                    "seule une demande approuvée peut devenir une commande."
                )})
        elif ancien_statut != StatutCommandeFournisseur.BROUILLON:
            if valeur_en_base(self, "fournisseur") != self.fournisseur_id:
                raise ValidationError({"fournisseur": "Le fournisseur ne peut plus être changé après l'envoi."})
        if self.pk and valeur_en_base(self, "demande_achat") != self.demande_achat_id:
            raise ValidationError({"demande_achat": "La demande d'achat d'origine ne peut pas être changée."})

    def verifier_suppression(self):
        if self.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValidationError("Seule une commande fournisseur en brouillon peut être supprimée ; sinon, annulez-la.")

    @property
    def montant_total(self):
        return sum((l.quantite_commandee * l.prix_unitaire for l in self.lignes.all()), start=0)

    def envoyer(self):
        if self.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValueError("Seule une commande en brouillon peut être envoyée.")
        if not self.lignes.exists():
            raise ValueError("Impossible d'envoyer une commande sans aucune ligne.")
        self.statut = StatutCommandeFournisseur.ENVOYEE
        self.save()


class LigneCommandeFournisseur(ValidationAvantEnregistrement, models.Model):
    commande = models.ForeignKey(
        CommandeFournisseur, verbose_name="Commande", on_delete=models.CASCADE,
        related_name="lignes",
    )
    article = models.ForeignKey(Article, verbose_name="Article", on_delete=models.PROTECT)
    unite = models.CharField(
        "Unité de commande", max_length=10, blank=True, default="",
        help_text="Unité d'achat (ex : SAC). Vide = unité d'achat de l'article, sinon son unité de stock. "
                  "Quantités et prix de la ligne sont dans cette unité ; le stock est converti à la réception.",
    )
    quantite_commandee = models.DecimalField("Quantité commandée", max_digits=14, decimal_places=3)
    prix_unitaire = models.DecimalField("Prix unitaire", max_digits=14, decimal_places=2)
    quantite_recue = models.DecimalField("Quantité reçue", max_digits=14, decimal_places=3, default=0)

    class Meta:
        verbose_name = "Ligne de commande fournisseur"
        verbose_name_plural = "Lignes de commande fournisseur"

    def __str__(self):
        return f"{self.commande.numero} : {self.quantite_commandee} {self.article.code}"

    @property
    def montant_ligne(self):
        return self.quantite_commandee * self.prix_unitaire

    @property
    def reste_a_recevoir(self):
        return self.quantite_commandee - self.quantite_recue

    @property
    def facteur_stock(self):
        """Nombre d'unités de stock dans une unité de commande (1 sac = 25 kg -> 25)."""
        from decimal import Decimal
        if not self.unite or self.unite == self.article.unite_mesure:
            return Decimal(1)
        from apps.referentiel.models import ConversionUnite
        return ConversionUnite.facteur_entre(self.unite, self.article.unite_mesure, self.article)

    def en_unite_de_stock(self, quantite):
        return quantite * self.facteur_stock

    def clean(self):
        """Les lignes ne se saisissent/modifient que tant que la commande est en brouillon."""
        if not self.unite and self.article_id:
            self.unite = self.article.unite_achat or self.article.unite_mesure
        if self.unite and self.article_id and self.unite != self.article.unite_mesure:
            from apps.referentiel.models import ConversionUnite, UniteMesure
            if self.unite not in UniteMesure.values:
                raise ValidationError({"unite": f"Unité « {self.unite} » inconnue."})
            if ConversionUnite.facteur_entre(self.unite, self.article.unite_mesure, self.article) is None:
                raise ValidationError({"unite": (
                    f"Aucune conversion de {self.unite} vers {self.article.unite_mesure} pour {self.article.code} : "
                    "paramétrez-la (référentiel > conversions) avant de commander dans cette unité."
                )})
        exiger_positif(self.quantite_commandee, "quantite_commandee", "La quantité commandée")
        exiger_positif(self.prix_unitaire, "prix_unitaire", "Le prix unitaire")
        if self.pk:
            ancienne = CommandeFournisseur.objects.filter(pk=valeur_en_base(self, "commande")).first()
            if ancienne and ancienne.statut != StatutCommandeFournisseur.BROUILLON:
                # Seule la mise à jour de quantite_recue par une réception est permise.
                if (valeur_en_base(self, "commande") != self.commande_id
                        or valeur_en_base(self, "article") != self.article_id
                        or valeur_en_base(self, "unite") not in ("", self.unite)
                        or valeur_en_base(self, "quantite_commandee") != self.quantite_commandee
                        or valeur_en_base(self, "prix_unitaire") != self.prix_unitaire):
                    raise ValidationError(
                        f"La commande {ancienne.numero} a été envoyée : ses lignes ne peuvent plus être modifiées."
                    )
        elif self.commande_id and self.commande.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValidationError({"commande": (
                f"La commande {self.commande.numero} a été envoyée : on ne peut plus y ajouter de ligne."
            )})
        if self.quantite_recue is not None and self.quantite_commandee is not None \
                and self.quantite_recue > self.quantite_commandee:
            raise ValidationError({"quantite_recue": "La quantité reçue dépasse la quantité commandée."})

    def verifier_suppression(self):
        if self.commande.statut != StatutCommandeFournisseur.BROUILLON:
            raise ValidationError("La commande a été envoyée : ses lignes ne peuvent plus être supprimées.")

    def save(self, *args, **kwargs):
        ancien_article = None if self._state.adding else valeur_en_base(self, "article")
        super().save(*args, **kwargs)
        # Quantité commandée = quantité en cours d'achat : le besoin ouvert suit.
        # (Une réception met aussi à jour la ligne ; le mouvement de stock qui
        # suit relance de toute façon le calcul.)
        articles = [self.article]
        if ancien_article and ancien_article != self.article_id:
            articles.append(Article.objects.get(pk=ancien_article))
        recalculer_besoins_articles(articles)

    def delete(self, *args, **kwargs):
        article = self.article
        resultat = super().delete(*args, **kwargs)
        recalculer_besoin_article(article)
        return resultat


class ReceptionAchat(ValidationAvantEnregistrement, models.Model):
    """
    Réception physique d'une commande fournisseur (déclenche un
    mouvement d'ENTREE en stock, voir apps/achats/views.py). Inclut le
    contrôle réception (onglet §6.1) : conformité constatée par le
    Magasinier ou le Responsable Achat à l'arrivée de la marchandise.
    """
    commande = models.ForeignKey(
        CommandeFournisseur, verbose_name="Commande", on_delete=models.PROTECT,
        related_name="receptions",
    )
    receptionne_par = models.ForeignKey(Utilisateur, verbose_name="Réceptionné par", on_delete=models.PROTECT)
    conforme = models.BooleanField(
        "Réception conforme", default=True,
        help_text="Contrôle réception : la livraison correspond-elle à la commande ? Non conforme = lots bloqués.",
    )
    depot = models.ForeignKey(
        "stocks.Depot", verbose_name="Lieu de réception", on_delete=models.PROTECT, null=True, blank=True,
        related_name="receptions_achats", help_text="Vide = « Magasin principal ».",
    )
    observations = models.TextField("Observations", blank=True)
    date_reception = models.DateTimeField("Date de réception", auto_now_add=True)

    class Meta:
        verbose_name = "Réception d'achat"
        verbose_name_plural = "Réceptions d'achats"
        ordering = ["-date_reception"]

    def __str__(self):
        return f"Réception {self.commande.numero} du {self.date_reception:%Y-%m-%d}"

    def clean(self):
        if self.pk and valeur_en_base(self, "commande") != self.commande_id:
            raise ValidationError({"commande": "La commande d'une réception ne peut pas être changée."})
        if self.pk is None and self.commande_id and self.commande.statut not in (
            StatutCommandeFournisseur.ENVOYEE, StatutCommandeFournisseur.PARTIELLEMENT_RECUE,
        ):
            raise ValidationError({"commande": (
                f"La commande {self.commande.numero} est {self.commande.get_statut_display().lower()} : "
                "seule une commande envoyée (ou partiellement reçue) peut être réceptionnée."
            )})

    def verifier_suppression(self):
        if self.lignes.exists() or self.retours.exists():
            raise ValidationError("Cette réception a déjà des lignes (stock mouvementé) : elle ne peut pas être supprimée.")


class LigneReceptionAchat(ValidationAvantEnregistrement, models.Model):
    """Détail par article reçu, pour mettre à jour quantite_recue de la ligne de commande correspondante."""
    reception = models.ForeignKey(
        ReceptionAchat, verbose_name="Réception", on_delete=models.CASCADE,
        related_name="lignes",
    )
    ligne_commande = models.ForeignKey(
        LigneCommandeFournisseur, verbose_name="Ligne de commande", on_delete=models.PROTECT,
        related_name="lignes_reception",
    )
    quantite_recue = models.DecimalField("Quantité reçue", max_digits=14, decimal_places=3)
    lot_fournisseur = models.CharField("N° lot fournisseur", max_length=60, blank=True)
    date_peremption = models.DateField("DLC / DLUO", null=True, blank=True)

    class Meta:
        verbose_name = "Ligne de réception"
        verbose_name_plural = "Lignes de réception"

    def __str__(self):
        return f"{self.reception} : {self.quantite_recue} {self.ligne_commande.article.code}"

    def clean(self):
        """
        - une ligne de réception ne se modifie pas (le stock est déjà entré) ;
        - quantité strictement positive, au plus le reste à recevoir ;
        - la ligne de commande doit appartenir à la commande réceptionnée.
        """
        if self.pk is not None:
            raise ValidationError("Une ligne de réception enregistrée ne peut pas être modifiée.")
        exiger_positif(self.quantite_recue, "quantite_recue", "La quantité reçue")
        if self.reception_id and self.ligne_commande_id:
            if self.ligne_commande.commande_id != self.reception.commande_id:
                raise ValidationError({"ligne_commande": (
                    "Cette ligne n'appartient pas à la commande de la réception "
                    f"({self.reception.commande.numero})."
                )})
            if self.reception.commande.statut not in (
                StatutCommandeFournisseur.ENVOYEE, StatutCommandeFournisseur.PARTIELLEMENT_RECUE,
            ):
                raise ValidationError({"reception": "La commande de cette réception n'est plus en attente de livraison."})
            reste = self.ligne_commande.reste_a_recevoir
            if self.quantite_recue > reste:
                raise ValidationError({"quantite_recue": (
                    f"Quantité reçue ({self.quantite_recue}) supérieure au reste à recevoir ({reste}) "
                    f"pour {self.ligne_commande.article.code}."
                )})

    def verifier_suppression(self):
        raise ValidationError("Une ligne de réception ne peut pas être supprimée (le stock a déjà été mouvementé).")

    def _creer_lot(self, depot, commande):
        """
        Traçabilité amont : chaque réception d'un article suivi par lot crée
        son lot matière (lot fournisseur, DLC). Réception non conforme : lot
        bloqué ; contrôle de réception prévu au plan qualité : lot « à
        contrôler » jusqu'à sa libération.

        Réception non conforme d'un article NON suivi par lot : un lot est
        quand même créé, bloqué, pour que la marchandise refusée reste
        indisponible (jusqu'à sa libération ou son retour au fournisseur)
        au lieu d'entrer directement dans le stock utilisable.
        """
        from django.utils import timezone
        from apps.stocks.models import LotMatiere, StatutLotMatiere
        article = self.ligne_commande.article
        if not article.suivi_par_lot and self.reception.conforme:
            return None
        from apps.qualite.models import controle_reception_requis
        statut = StatutLotMatiere.LIBERE
        if not self.reception.conforme:
            statut = StatutLotMatiere.BLOQUE
        elif controle_reception_requis(article):
            statut = StatutLotMatiere.A_CONTROLER
        lot = LotMatiere(
            article=article, depot=depot, lot_fournisseur=self.lot_fournisseur,
            fournisseur=commande.fournisseur, ligne_reception=self,
            date_reception=timezone.localdate(), date_peremption=self.date_peremption,
            quantite_initiale=self.quantite_recue * self.ligne_commande.facteur_stock, statut=StatutLotMatiere.LIBERE,
        )
        lot.save()
        if statut != StatutLotMatiere.LIBERE:
            lot.changer_statut(statut)
        if statut == StatutLotMatiere.A_CONTROLER:
            from apps.qualite.models import generer_controles_reception
            generer_controles_reception(lot)
        return lot

    def save(self, *args, **kwargs):
        """
        Enregistre la ligne ET ses conséquences (quantité reçue de la
        ligne de commande, statut de la commande, entrée en stock) en
        une seule transaction : tout ou rien.
        """
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        with transaction.atomic():
            creation = self._state.adding
            super().save(*args, **kwargs)
            if not creation:
                return
            ligne_commande = LigneCommandeFournisseur.objects.select_for_update().get(pk=self.ligne_commande_id)
            ligne_commande.quantite_recue += self.quantite_recue
            ligne_commande.save()

            commande = ligne_commande.commande
            totaux = commande.lignes.aggregate(commande=Sum("quantite_commandee"), recu=Sum("quantite_recue"))
            commande.statut = (
                StatutCommandeFournisseur.RECUE if totaux["recu"] >= totaux["commande"]
                else StatutCommandeFournisseur.PARTIELLEMENT_RECUE
            )
            commande.save()

            depot = self.reception.depot or depot_par_defaut("Magasin principal")
            # Ligne en unité d'achat (sacs...) -> stock en unité de stock (kg...).
            facteur = ligne_commande.facteur_stock
            MouvementStock.objects.create(
                article=ligne_commande.article,
                depot=depot,
                type_mouvement=TypeMouvement.ENTREE,
                quantite=self.quantite_recue * facteur,
                cout_unitaire=ligne_commande.prix_unitaire / facteur,   # prix d'achat ramené à l'unité de stock
                motif=f"Réception achat {self.reception_id} - commande {commande.numero}"
                      + (f" ({self.quantite_recue} {ligne_commande.unite})" if facteur != 1 else ""),
                document_origine=commande.numero,
                utilisateur=self.reception.receptionne_par,
            )
            self._creer_lot(depot, commande)
            from apps.comptabilite.ecritures import ecrire_reception
            ecrire_reception(self)


class MotifRetourFournisseur(models.TextChoices):
    NON_CONFORME = "NON_CONFORME", "Non conforme"
    ENDOMMAGE = "ENDOMMAGE", "Endommagé au transport"
    QUANTITE_EXCEDENTAIRE = "QUANTITE_EXCEDENTAIRE", "Quantité excédentaire livrée"
    ERREUR_REFERENCE = "ERREUR_REFERENCE", "Erreur de référence"
    AUTRE = "AUTRE", "Autre"


class RetourFournisseur(ValidationAvantEnregistrement, models.Model):
    """Onglet "retours fournisseurs" du §6.1 : marchandise reçue puis retournée au fournisseur."""
    reception = models.ForeignKey(
        ReceptionAchat, verbose_name="Réception concernée", on_delete=models.PROTECT,
        related_name="retours",
    )
    article = models.ForeignKey(Article, verbose_name="Article retourné", on_delete=models.PROTECT)
    quantite_retournee = models.DecimalField(
        "Quantité retournée", max_digits=14, decimal_places=3,
        help_text="Dans l'unité de la commande (ex : sacs), comme la quantité reçue.",
    )
    motif = models.CharField("Motif", max_length=25, choices=MotifRetourFournisseur.choices)
    observations = models.TextField("Observations", blank=True)
    traite_par = models.ForeignKey(Utilisateur, verbose_name="Traité par", on_delete=models.PROTECT)
    date_retour = models.DateTimeField("Date de retour", auto_now_add=True)

    class Meta:
        verbose_name = "Retour fournisseur"
        verbose_name_plural = "Retours fournisseurs"
        ordering = ["-date_retour"]

    def __str__(self):
        return f"Retour {self.quantite_retournee} {self.article.code} - {self.get_motif_display()}"

    def clean(self):
        """
        On ne retourne que ce qui a été reçu dans CETTE réception, moins
        ce qui a déjà été retourné.
        """
        if self.pk is not None:
            raise ValidationError("Un retour fournisseur enregistré ne peut pas être modifié.")
        exiger_positif(self.quantite_retournee, "quantite_retournee", "La quantité retournée")
        if self.reception_id and self.article_id:
            recu = self.reception.lignes.filter(
                ligne_commande__article_id=self.article_id,
            ).aggregate(total=Sum("quantite_recue"))["total"] or 0
            if recu == 0:
                raise ValidationError({"article": f"L'article {self.article.code} n'a pas été reçu dans cette réception."})
            deja_retourne = RetourFournisseur.objects.filter(
                reception_id=self.reception_id, article_id=self.article_id,
            ).aggregate(total=Sum("quantite_retournee"))["total"] or 0
            retournable = recu - deja_retourne
            if self.quantite_retournee > retournable:
                raise ValidationError({"quantite_retournee": (
                    f"Retour impossible : {retournable} de {self.article.code} au plus peut encore être retourné "
                    f"(reçu {recu}, déjà retourné {deja_retourne})."
                )})

    def verifier_suppression(self):
        raise ValidationError("Un retour fournisseur ne peut pas être supprimé (le stock a déjà été mouvementé).")

    def save(self, *args, **kwargs):
        """La marchandise retournée quitte physiquement le magasin : sortie de stock dans la même transaction."""
        from apps.stocks.models import MouvementStock, TypeMouvement, depot_par_defaut
        with transaction.atomic():
            creation = self._state.adding
            super().save(*args, **kwargs)
            if creation:
                from apps.stocks.models import LotMatiere
                ligne_commande = self.reception.commande.lignes.filter(article_id=self.article_id).first()
                facteur = ligne_commande.facteur_stock if ligne_commande else 1
                reste = self.quantite_retournee * facteur
                for lot in LotMatiere.objects.select_for_update().filter(
                    ligne_reception__reception_id=self.reception_id, article_id=self.article_id, quantite_restante__gt=0,
                ).order_by("pk"):
                    if reste <= 0:
                        break
                    prise = min(lot.quantite_restante, reste)
                    lot.retirer(prise)
                    reste -= prise
                MouvementStock.objects.create(
                    article=self.article,
                    depot=self.reception.depot or depot_par_defaut("Magasin principal"),
                    type_mouvement=TypeMouvement.SORTIE,
                    quantite=self.quantite_retournee * facteur,
                    motif=f"Retour fournisseur ({self.get_motif_display()}) - commande {self.reception.commande.numero}",
                    document_origine=self.reception.commande.numero,
                    utilisateur=self.traite_par,
                )
                # Contre-passation de l'écriture de réception (dette fournisseur / achat).
                from apps.comptabilite.ecritures import ecrire_retour_fournisseur
                ecrire_retour_fournisseur(self)
