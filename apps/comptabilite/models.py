"""
Module 11 - Pilotage / Comptabilité.

Utilisé par la Comptabilité/DAF (accès transversal en lecture/contrôle
à tous les modules) et la Direction (tableaux de bord). Contient :
- AnomalieDetectee : les contrôles automatiques (§14.3)
- ExportComptable : exports vers Sage 100 (voir README pour le niveau
  d'intégration retenu : export fichier ou API)
- Cloture : clôtures mensuelles/annuelles
"""

from django.db import models
from apps.comptes.models import Utilisateur


class TypeAnomalie(models.TextChoices):
    ECART_STOCK = "ECART_STOCK", "Écart de stock non justifié"
    ECART_CAISSE = "ECART_CAISSE", "Écart de caisse non justifié"
    DEPASSEMENT_MATIERE = "DEPASSEMENT_MATIERE", "Dépassement de sortie matière"
    LOT_NON_LIBERE_VENDU = "LOT_NON_LIBERE_VENDU", "Tentative de vente d'un lot non libéré"
    COMMANDE_CLIENT_BLOQUE = "COMMANDE_CLIENT_BLOQUE", "Commande sur client bloqué"
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


class ExportComptable(models.Model):
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


class TypeCloture(models.TextChoices):
    MENSUELLE = "MENSUELLE", "Mensuelle"
    ANNUELLE = "ANNUELLE", "Annuelle"


class Cloture(models.Model):
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
