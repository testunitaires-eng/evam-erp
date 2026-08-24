"""
Module 8 - Caisse.

Le Caissier "ne peut pas modifier commande, prix, stock, ni supprimer
un écart — il doit le justifier". Ces règles sont appliquées via les
permissions (voir views.py) et via l'absence de champs modifiables
directement sur la commande/le stock depuis ce module.
"""

from django.db import models
from apps.comptes.models import Utilisateur
from apps.commercial.models import Facture
from apps.core.models import generer_numero


class Caisse(models.Model):
    nom = models.CharField("Nom de la caisse", max_length=100)
    emplacement = models.CharField("Emplacement", max_length=150, blank=True)
    actif = models.BooleanField("Active", default=True)

    class Meta:
        verbose_name = "Caisse"
        verbose_name_plural = "Caisses"

    def __str__(self):
        return self.nom


class StatutSession(models.TextChoices):
    OUVERTE = "OUVERTE", "Ouverte"
    CLOTUREE = "CLOTUREE", "Clôturée"


class SessionCaisse(models.Model):
    """
    Une session = une ouverture de caisse par un caissier jusqu'à sa
    clôture. L'écart entre solde théorique et solde réel compté est
    calculé automatiquement à la clôture (§11.3).
    """
    caisse = models.ForeignKey(Caisse, verbose_name="Caisse", on_delete=models.PROTECT)
    caissier = models.ForeignKey(Utilisateur, verbose_name="Caissier", on_delete=models.PROTECT)
    solde_ouverture = models.DecimalField("Solde d'ouverture", max_digits=14, decimal_places=2)
    solde_theorique_cloture = models.DecimalField(
        "Solde théorique à la clôture", max_digits=14, decimal_places=2,
        null=True, blank=True,
    )
    solde_compte_cloture = models.DecimalField(
        "Solde compté à la clôture", max_digits=14, decimal_places=2,
        null=True, blank=True,
    )
    statut = models.CharField("Statut", max_length=15, choices=StatutSession.choices, default=StatutSession.OUVERTE)
    date_ouverture = models.DateTimeField("Date d'ouverture", auto_now_add=True)
    date_cloture = models.DateTimeField("Date de clôture", null=True, blank=True)

    class Meta:
        verbose_name = "Session de caisse"
        verbose_name_plural = "Sessions de caisse"
        ordering = ["-date_ouverture"]

    def __str__(self):
        return f"Session {self.caisse.nom} - {self.caissier} ({self.get_statut_display()})"

    @property
    def ecart(self):
        if self.solde_theorique_cloture is None or self.solde_compte_cloture is None:
            return None
        return self.solde_compte_cloture - self.solde_theorique_cloture

    def cloturer(self, solde_theorique, solde_compte):
        """
        Clôture la session. Si un écart existe, il doit obligatoirement
        être justifié via EcartCaisse (voir vue caisse).
        """
        from django.utils import timezone
        self.solde_theorique_cloture = solde_theorique
        self.solde_compte_cloture = solde_compte
        self.statut = StatutSession.CLOTUREE
        self.date_cloture = timezone.now()
        self.save()


class ModePaiement(models.TextChoices):
    ESPECES = "ESPECES", "Espèces"
    MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"
    VIREMENT = "VIREMENT", "Virement"
    CHEQUE = "CHEQUE", "Chèque"


class Encaissement(models.Model):
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    session_caisse = models.ForeignKey(
        SessionCaisse, verbose_name="Session de caisse", on_delete=models.PROTECT,
        related_name="encaissements",
    )
    facture = models.ForeignKey(Facture, verbose_name="Facture", on_delete=models.PROTECT, related_name="encaissements")
    montant = models.DecimalField("Montant encaissé", max_digits=14, decimal_places=2)
    mode_paiement = models.CharField("Mode de paiement", max_length=15, choices=ModePaiement.choices)
    date_encaissement = models.DateTimeField("Date d'encaissement", auto_now_add=True)

    class Meta:
        verbose_name = "Encaissement"
        verbose_name_plural = "Encaissements"
        ordering = ["-date_encaissement"]

    def __str__(self):
        return f"{self.numero} - {self.montant} ({self.get_mode_paiement_display()})"

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("ENC")
        super().save(*args, **kwargs)


class EcartCaisse(models.Model):
    """
    Justification obligatoire d'un écart de caisse. Le caissier ne
    peut jamais supprimer un écart : il ne peut que le justifier
    (règle explicite du cahier des charges).
    """
    session_caisse = models.OneToOneField(
        SessionCaisse, verbose_name="Session de caisse", on_delete=models.CASCADE,
        related_name="justification_ecart",
    )
    montant_ecart = models.DecimalField("Montant de l'écart", max_digits=14, decimal_places=2)
    justification = models.TextField("Justification")
    valide_par = models.ForeignKey(
        Utilisateur, verbose_name="Validé par", on_delete=models.PROTECT,
        null=True, blank=True,
        help_text="Rempli par la Comptabilité/DAF après contrôle.",
    )
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)

    class Meta:
        verbose_name = "Justification d'écart de caisse"
        verbose_name_plural = "Justifications d'écarts de caisse"

    def __str__(self):
        return f"Écart {self.montant_ecart} - session {self.session_caisse_id}"
