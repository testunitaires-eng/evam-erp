"""
Module 11 - Pilotage / Comptabilité.

Utilisé par la Comptabilité/DAF (accès transversal en lecture/contrôle
à tous les modules) et la Direction (tableaux de bord). Contient :
- AnomalieDetectee : les contrôles automatiques (§14.3)
- ExportComptable : exports vers Sage 100 (voir README pour le niveau
  d'intégration retenu : export fichier ou API)
- Cloture : clôtures mensuelles/annuelles
"""

import re

from django.core.exceptions import ValidationError

from django.db import models
from apps.comptes.models import Utilisateur
from apps.core.validation import ValidationAvantEnregistrement, exiger_ordre_dates


class TypeAnomalie(models.TextChoices):
    ECART_STOCK = "ECART_STOCK", "Écart de stock non justifié"
    ECART_CAISSE = "ECART_CAISSE", "Écart de caisse non justifié"
    DEPASSEMENT_MATIERE = "DEPASSEMENT_MATIERE", "Dépassement de sortie matière"
    LOT_NON_LIBERE_VENDU = "LOT_NON_LIBERE_VENDU", "Tentative de vente d'un lot non libéré"
    COMMANDE_CLIENT_BLOQUE = "COMMANDE_CLIENT_BLOQUE", "Commande sur client bloqué"
    IMPAYE = "IMPAYE", "Facture échue impayée"
    STOCK_SOUS_MINIMUM = "STOCK_SOUS_MINIMUM", "Stock sous le minimum"
    LOT_PERIME = "LOT_PERIME", "Lot périmé ou proche de la péremption"
    SESSION_NON_CLOTUREE = "SESSION_NON_CLOTUREE", "Session de caisse non clôturée"
    DECAISSEMENT_EN_ATTENTE = "DECAISSEMENT_EN_ATTENTE", "Décaissement en attente d'autorisation"
    AUTRE = "AUTRE", "Autre anomalie"


class StatutAnomalie(models.TextChoices):
    DETECTEE = "DETECTEE", "Détectée"
    EN_TRAITEMENT = "EN_TRAITEMENT", "En traitement"
    TRAITEE = "TRAITEE", "Traitée"
    IGNOREE = "IGNOREE", "Ignorée (justifiée)"


class AnomalieDetectee(models.Model):
    """
    Une anomalie remontée par les contrôles automatiques du système
    (§14.3 du cahier des charges liste 14 types de contrôles).
    La liste TypeAnomalie ci-dessus est un point de départ à compléter
    avec le client selon les 14 contrôles exacts attendus.
    """
    type_anomalie = models.CharField("Type d'anomalie", max_length=30, choices=TypeAnomalie.choices)
    module_source = models.CharField("Module source", max_length=50)
    description = models.TextField("Description")
    statut = models.CharField("Statut", max_length=20, choices=StatutAnomalie.choices, default=StatutAnomalie.DETECTEE)
    traite_par = models.ForeignKey(
        Utilisateur, verbose_name="Traitée par", on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    date_detection = models.DateTimeField("Date de détection", auto_now_add=True)
    date_traitement = models.DateTimeField("Date de traitement", null=True, blank=True)
    commentaire_traitement = models.TextField("Commentaire de traitement", blank=True)
    type_document = models.CharField("Type de document", max_length=60, blank=True)
    document_id = models.PositiveBigIntegerField("Identifiant du document", null=True, blank=True)
    reference = models.CharField("Référence du document", max_length=50, blank=True)
    cle = models.CharField(
        "Clé de détection", max_length=100, blank=True, db_index=True,
        help_text="Identifie le cas détecté (ex : impaye-FACT-000012) : pas de doublon tant qu'il est ouvert.",
    )

    class Meta:
        verbose_name = "Anomalie détectée"
        verbose_name_plural = "Anomalies détectées"
        ordering = ["-date_detection"]

    def __str__(self):
        return f"{self.get_type_anomalie_display()} ({self.get_statut_display()})"


class TypeExport(models.TextChoices):
    VENTES = "VENTES", "Ventes"
    ENCAISSEMENTS = "ENCAISSEMENTS", "Encaissements"
    ACHATS = "ACHATS", "Achats"
    JOURNAL = "JOURNAL", "Journal comptable"


class ExportComptable(ValidationAvantEnregistrement, models.Model):
    """
    Export comptable vers Sage 100. Dans cette version, l'export est
    généré comme un fichier téléchargeable (CSV/Excel) — voir
    README.md pour la discussion "export fichier vs interface API"
    à trancher avec le client (§14.2).
    """
    type_export = models.CharField("Type d'export", max_length=20, choices=TypeExport.choices)
    periode_debut = models.DateField("Début de période")
    periode_fin = models.DateField("Fin de période")
    fichier = models.FileField("Fichier généré", upload_to="exports_comptables/", null=True, blank=True)
    genere_par = models.ForeignKey(Utilisateur, verbose_name="Généré par", on_delete=models.PROTECT)
    date_generation = models.DateTimeField("Date de génération", auto_now_add=True)

    class Meta:
        verbose_name = "Export comptable"
        verbose_name_plural = "Exports comptables"
        ordering = ["-date_generation"]

    def __str__(self):
        return f"Export {self.get_type_export_display()} {self.periode_debut} - {self.periode_fin}"

    def clean(self):
        exiger_ordre_dates(self.periode_debut, self.periode_fin, "periode_fin", "le début de période", "La fin de période")


class TypeCloture(models.TextChoices):
    MENSUELLE = "MENSUELLE", "Mensuelle"
    ANNUELLE = "ANNUELLE", "Annuelle"


class Cloture(ValidationAvantEnregistrement, models.Model):
    """
    Une clôture verrouille une période : plus aucune modification des
    documents de cette période n'est possible après clôture (règle
    classique de gestion, à confirmer avec le client).
    """
    periode = models.CharField("Période", max_length=20, help_text="Format AAAA-MM ou AAAA")
    type_cloture = models.CharField("Type de clôture", max_length=15, choices=TypeCloture.choices)
    valide_par = models.ForeignKey(Utilisateur, verbose_name="Validée par", on_delete=models.PROTECT)
    date_cloture = models.DateTimeField("Date de clôture", auto_now_add=True)

    class Meta:
        verbose_name = "Clôture"
        verbose_name_plural = "Clôtures"

    def __str__(self):
        return f"Clôture {self.get_type_cloture_display()} {self.periode}"

    def clean(self):
        formats = {TypeCloture.MENSUELLE: (r"\d{4}-(0[1-9]|1[0-2])", "AAAA-MM"), TypeCloture.ANNUELLE: (r"\d{4}", "AAAA")}
        motif, libelle = formats.get(self.type_cloture, (None, None))
        if motif and not re.fullmatch(motif, self.periode or ""):
            raise ValidationError({"periode": f"Pour une clôture {self.get_type_cloture_display().lower()}, la période doit être au format {libelle}."})
        if Cloture.objects.filter(type_cloture=self.type_cloture, periode=self.periode).exclude(pk=self.pk).exists():
            raise ValidationError({"periode": "Cette période est déjà clôturée."})


# =====================================================================
# Écritures comptables automatiques (plan SYSCOHADA révisé par défaut)
# =====================================================================

class CleCompte(models.TextChoices):
    """Rôle de chaque compte utilisé par les écritures automatiques."""
    CLIENTS = "CLIENTS", "Clients"
    FOURNISSEURS = "FOURNISSEURS", "Fournisseurs"
    VENTES_PRODUITS_FINIS = "VENTES_PRODUITS_FINIS", "Ventes de produits finis (si l'article n'a pas de compte de vente)"
    TVA_COLLECTEE = "TVA_COLLECTEE", "TVA facturée sur ventes"
    ACCISES = "ACCISES", "Droits d'accises"
    CENTIMES_ADDITIONNELS = "CENTIMES_ADDITIONNELS", "Centimes additionnels"
    RABAIS_ACCORDES = "RABAIS_ACCORDES", "Rabais, remises, ristournes accordés (avoirs)"
    ACHATS_MATIERES = "ACHATS_MATIERES", "Achats de matières premières et fournitures"
    CAISSE = "CAISSE", "Caisse (espèces)"
    BANQUE = "BANQUE", "Banque (virement, chèque)"
    MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"
    CHARGES_DIVERSES = "CHARGES_DIVERSES", "Charges diverses (décaissements)"


# Valeurs proposées par défaut (SYSCOHADA révisé) : à valider par le DAF,
# modifiables à tout moment sans toucher au code (/api/comptabilite/comptes/).
COMPTES_PAR_DEFAUT = {
    CleCompte.CLIENTS: "411",
    CleCompte.FOURNISSEURS: "401",
    CleCompte.VENTES_PRODUITS_FINIS: "702",
    CleCompte.TVA_COLLECTEE: "4431",
    CleCompte.ACCISES: "4478",
    CleCompte.CENTIMES_ADDITIONNELS: "4479",
    CleCompte.RABAIS_ACCORDES: "709",
    CleCompte.ACHATS_MATIERES: "602",
    CleCompte.CAISSE: "571",
    CleCompte.BANQUE: "521",
    CleCompte.MOBILE_MONEY: "5215",
    CleCompte.CHARGES_DIVERSES: "658",
}


class CompteParametre(models.Model):
    """Numéro de compte général associé à chaque rôle (paramétrage du DAF)."""
    cle = models.CharField("Rôle", max_length=30, choices=CleCompte.choices, unique=True)
    numero = models.CharField("Numéro de compte", max_length=20)

    class Meta:
        verbose_name = "Compte comptable paramétré"
        verbose_name_plural = "Comptes comptables paramétrés"
        ordering = ["cle"]

    def __str__(self):
        return f"{self.get_cle_display()} : {self.numero}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if not re.fullmatch(r"\d{2,20}", self.numero or ""):
            raise ValidationError({"numero": "Un numéro de compte ne contient que des chiffres (au moins 2)."})

    @classmethod
    def numero_de(cls, cle):
        parametre = cls.objects.filter(cle=cle).first()
        return parametre.numero if parametre else COMPTES_PAR_DEFAUT[cle]


class Journal(models.TextChoices):
    VENTES = "VT", "Ventes"
    ACHATS = "AC", "Achats"
    CAISSE = "CA", "Caisse / Trésorerie"
    OPERATIONS_DIVERSES = "OD", "Opérations diverses"


class EcritureComptable(models.Model):
    """
    Une écriture générée automatiquement par un document (facture,
    encaissement, décaissement, avoir, réception d'achat). Toujours
    équilibrée (total débit = total crédit), jamais saisie ni modifiée à
    la main : une erreur se corrige par l'annulation du document, qui
    génère l'écriture inverse (contre-passation).
    """
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    journal = models.CharField("Journal", max_length=2, choices=Journal.choices)
    date = models.DateField("Date comptable")
    piece = models.CharField("Pièce (document d'origine)", max_length=50)
    libelle = models.CharField("Libellé", max_length=255)
    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.PROTECT)
    objet_id = models.PositiveBigIntegerField()
    date_creation = models.DateTimeField("Créée le", auto_now_add=True)
    exportee_le = models.DateTimeField("Exportée vers Sage le", null=True, blank=True)

    class Meta:
        verbose_name = "Écriture comptable"
        verbose_name_plural = "Écritures comptables"
        ordering = ["date", "numero"]
        indexes = [models.Index(fields=["content_type", "objet_id"])]

    def __str__(self):
        return f"{self.numero} [{self.journal}] {self.piece} - {self.libelle}"


class LigneEcriture(models.Model):
    ecriture = models.ForeignKey(EcritureComptable, on_delete=models.CASCADE, related_name="lignes")
    compte = models.CharField("Compte général", max_length=20)
    compte_tiers = models.CharField("Compte tiers", max_length=30, blank=True)
    libelle = models.CharField("Libellé", max_length=255)
    debit = models.DecimalField("Débit", max_digits=16, decimal_places=2, default=0)
    credit = models.DecimalField("Crédit", max_digits=16, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Ligne d'écriture"
        verbose_name_plural = "Lignes d'écriture"

    def __str__(self):
        return f"{self.compte} D {self.debit} / C {self.credit}"


# =====================================================================
# Seuils des contrôles automatiques (réglés par la Comptabilité/DAF)
# =====================================================================

class CleControle(models.TextChoices):
    TOLERANCE_DEPASSEMENT_MATIERE = "TOLERANCE_DEPASSEMENT_MATIERE", "Tolérance de dépassement matière (%)"
    DELAI_ALERTE_PEREMPTION_JOURS = "DELAI_ALERTE_PEREMPTION_JOURS", "Alerte péremption : nombre de jours avant la date"
    DELAI_DECAISSEMENT_EN_ATTENTE_JOURS = "DELAI_DECAISSEMENT_EN_ATTENTE_JOURS", "Décaissement en attente : alerte après (jours)"


# Valeur par défaut, minimum, maximum, entier obligatoire.
CONTROLES_PAR_DEFAUT = {
    CleControle.TOLERANCE_DEPASSEMENT_MATIERE: (5, 0, 100, False),
    CleControle.DELAI_ALERTE_PEREMPTION_JOURS: (7, 0, 365, True),
    CleControle.DELAI_DECAISSEMENT_EN_ATTENTE_JOURS: (2, 0, 90, True),
}


class ParametreControle(models.Model):
    """Seuil d'un contrôle automatique d'anomalie, modifiable par la Comptabilité/DAF sans redéploiement."""
    cle = models.CharField("Contrôle", max_length=50, choices=CleControle.choices, unique=True)
    valeur = models.DecimalField("Valeur", max_digits=8, decimal_places=2)
    modifie_par = models.ForeignKey(
        Utilisateur, verbose_name="Modifié par", on_delete=models.SET_NULL, null=True, blank=True,
    )
    date_modification = models.DateTimeField("Modifié le", auto_now=True)

    class Meta:
        verbose_name = "Seuil de contrôle automatique"
        verbose_name_plural = "Seuils des contrôles automatiques"
        ordering = ["cle"]

    def __str__(self):
        return f"{self.get_cle_display()} : {self.valeur}"

    def clean(self):
        _, minimum, maximum, entier = CONTROLES_PAR_DEFAUT[self.cle]
        if self.valeur is None or not (minimum <= self.valeur <= maximum):
            raise ValidationError({"valeur": f"La valeur doit être comprise entre {minimum} et {maximum}."})
        if entier and self.valeur != int(self.valeur):
            raise ValidationError({"valeur": "Ce seuil est un nombre de jours entier."})

    @classmethod
    def valeur_de(cls, cle):
        from decimal import Decimal
        parametre = cls.objects.filter(cle=cle).first()
        return parametre.valeur if parametre else Decimal(CONTROLES_PAR_DEFAUT[cle][0])
