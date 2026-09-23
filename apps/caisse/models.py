"""
Module 8 - Caisse.

Le Caissier "ne peut pas modifier commande, prix, stock, ni supprimer
un écart — il doit le justifier". Ces règles sont appliquées via les
permissions (voir views.py) et via l'absence de champs modifiables
directement sur la commande/le stock depuis ce module.
"""

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur, Profil
from apps.commercial.models import Facture, StatutFacture
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, valeur_en_base, convertir_decimal,
)


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


class SessionCaisse(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        """
        - solde d'ouverture positif ou nul ;
        - on n'ouvre une session que sur une caisse active, et une seule
          session ouverte à la fois par caisse ;
        - une session clôturée est figée ; caisse et solde d'ouverture
          ne changent plus une fois des mouvements enregistrés.
        """
        exiger_positif(self.solde_ouverture, "solde_ouverture", "Le solde d'ouverture", strict=False)
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutSession.CLOTUREE:
            raise ValidationError("Cette session de caisse est clôturée : elle ne peut plus être modifiée.")
        if ancien_statut is None:
            if self.statut != StatutSession.OUVERTE:
                raise ValidationError({"statut": "Une session de caisse est toujours créée ouverte."})
            if self.caisse_id:
                if not self.caisse.actif:
                    raise ValidationError({"caisse": f"La caisse « {self.caisse.nom} » est inactive."})
                if SessionCaisse.objects.filter(caisse_id=self.caisse_id, statut=StatutSession.OUVERTE).exists():
                    raise ValidationError({"caisse": (
                        f"La caisse « {self.caisse.nom} » a déjà une session ouverte : "
                        "clôturez-la avant d'en ouvrir une nouvelle."
                    )})
        else:
            if valeur_en_base(self, "caisse") != self.caisse_id:
                raise ValidationError({"caisse": "La caisse d'une session ne peut pas être changée."})
            if valeur_en_base(self, "solde_ouverture") != self.solde_ouverture and (
                self.encaissements.exists() or self.decaissements.exists()
            ):
                raise ValidationError({"solde_ouverture": (
                    "Le solde d'ouverture ne peut plus être modifié : des mouvements "
                    "ont déjà été enregistrés sur cette session."
                )})

    def verifier_suppression(self):
        if self.statut == StatutSession.CLOTUREE or self.encaissements.exists() or self.decaissements.exists():
            raise ValidationError("Une session clôturée ou comportant des mouvements ne peut pas être supprimée.")

    # @property
    # def ecart(self):
    #     if self.solde_theorique_cloture is None or self.solde_compte_cloture is None:
    #         return None
    #     return self.solde_compte_cloture - self.solde_theorique_cloture

    # def cloturer(self, solde_theorique, solde_compte):
    #     """
    #     Clôture la session. Si un écart existe, il doit obligatoirement
    #     être justifié via EcartCaisse (voir vue caisse).
    #     """
    #     from django.utils import timezone
    #     self.solde_theorique_cloture = solde_theorique
    #     self.solde_compte_cloture = solde_compte
    #     self.statut = StatutSession.CLOTUREE
    #     self.date_cloture = timezone.now()
    #     self.save()



    @property
    def ecart(self):
        if self.solde_theorique_cloture is None or self.solde_compte_cloture is None:
            return None
        return self.solde_compte_cloture - self.solde_theorique_cloture

    def calculer_solde_theorique(self):
        """
        §9.2 : solde théorique = ouverture + encaissements - décaissements.
        Utilisé par défaut à la clôture si aucun solde_theorique n'est
        fourni explicitement.
        """
        from django.db.models import Sum
        total_encaissements = self.encaissements.aggregate(total=Sum("montant"))["total"] or 0
        total_decaissements = self.decaissements.aggregate(total=Sum("montant"))["total"] or 0
        return self.solde_ouverture + total_encaissements - total_decaissements

    @transaction.atomic
    def cloturer(self, solde_compte):
        """
        Clôture la session. Le solde théorique est TOUJOURS calculé par
        le système (ouverture + encaissements - décaissements) : il n'est
        plus accepté en saisie, sinon un écart pourrait être masqué en
        saisissant un théorique égal au compté.
        Si un écart existe, il doit obligatoirement être justifié via
        EcartCaisse (voir vue caisse). Lève ValueError si la session est
        déjà clôturée ou si le solde compté est absent/invalide.
        """
        from django.utils import timezone
        if self.statut != StatutSession.OUVERTE:
            raise ValueError("Cette session est déjà clôturée.")
        solde_compte = convertir_decimal(solde_compte, "Le solde compté (solde_compte)", strict=False)
        self.solde_theorique_cloture = self.calculer_solde_theorique()
        self.solde_compte_cloture = solde_compte
        self.statut = StatutSession.CLOTUREE
        self.date_cloture = timezone.now()
        self.save()

class ModePaiement(models.TextChoices):
    ESPECES = "ESPECES", "Espèces"
    MOBILE_MONEY = "MOBILE_MONEY", "Mobile Money"
    VIREMENT = "VIREMENT", "Virement"
    CHEQUE = "CHEQUE", "Chèque"


class Encaissement(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        """
        - un encaissement ne se modifie pas après coup ;
        - montant strictement positif ;
        - uniquement sur une session OUVERTE ;
        - jamais sur une facture annulée, ni au-delà du solde restant dû.
        """
        if self.pk is not None:
            raise ValidationError("Un encaissement enregistré ne peut pas être modifié.")
        exiger_positif(self.montant, "montant", "Le montant encaissé")
        if self.session_caisse_id and self.session_caisse.statut != StatutSession.OUVERTE:
            raise ValidationError({"session_caisse": "Cette session de caisse est clôturée : aucun encaissement possible."})
        if self.facture_id:
            facture = self.facture
            if facture.statut == StatutFacture.ANNULEE:
                raise ValidationError({"facture": f"La facture {facture.numero} est annulée : aucun encaissement possible."})
            if self.montant > facture.solde_restant:
                raise ValidationError({"montant": (
                    f"Le montant encaissé ({self.montant}) dépasse le solde restant dû "
                    f"sur la facture {facture.numero} ({facture.solde_restant})."
                )})

    def verifier_suppression(self):
        raise ValidationError("Un encaissement ne peut pas être supprimé.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.numero:
                self.numero = generer_numero("ENC")
            super().save(*args, **kwargs)
            self.facture.mettre_a_jour_statut_paiement()


class EcartCaisse(ValidationAvantEnregistrement, models.Model):
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

    def clean(self):
        """
        - on ne justifie que l'écart réel d'une session CLÔTURÉE : le
          montant est repris automatiquement de la session (pas saisi) ;
        - justification obligatoire ;
        - une fois validé par la Comptabilité/DAF, l'écart est figé.
        """
        if valeur_en_base(self, "valide_par") is not None:
            raise ValidationError("Cet écart a déjà été validé par la Comptabilité : il ne peut plus être modifié.")
        if self.session_caisse_id:
            session = self.session_caisse
            if session.statut != StatutSession.CLOTUREE:
                raise ValidationError({"session_caisse": "La session doit être clôturée avant de justifier son écart."})
            if not session.ecart:
                raise ValidationError({"session_caisse": "Cette session n'a aucun écart à justifier."})
            self.montant_ecart = session.ecart
        if not (self.justification or "").strip():
            raise ValidationError({"justification": "La justification de l'écart est obligatoire."})
        if self.valide_par_id and self.valide_par.profil not in (Profil.COMPTABILITE_DAF, Profil.ADMIN_SI) \
                and not self.valide_par.is_superuser:
            raise ValidationError({"valide_par": "Seule la Comptabilité/DAF peut valider un écart de caisse."})






class Decaissement(ValidationAvantEnregistrement, models.Model):
    """
    §9.1/§9.2 : sortie de caisse autorisée (remboursement client,
    dépense de fonctionnement...), distincte d'un encaissement.
    Toujours rattachée à une session et à un motif ; nécessite une
    autorisation (le caissier seul ne peut pas sortir d'argent sans
    validation).
    """
    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    session_caisse = models.ForeignKey(
        SessionCaisse, verbose_name="Session de caisse", on_delete=models.PROTECT,
        related_name="decaissements",
    )
    montant = models.DecimalField("Montant", max_digits=14, decimal_places=2)
    motif = models.TextField("Motif")
    beneficiaire = models.CharField("Bénéficiaire", max_length=200, blank=True)
    autorise_par = models.ForeignKey(
        Utilisateur, verbose_name="Autorisé par", on_delete=models.PROTECT,
        related_name="decaissements_autorises",
    )
    effectue_par = models.ForeignKey(
        Utilisateur, verbose_name="Effectué par (caissier)", on_delete=models.PROTECT,
        related_name="decaissements_effectues",
    )
    date_decaissement = models.DateTimeField("Date", auto_now_add=True)

    class Meta:
        verbose_name = "Décaissement"
        verbose_name_plural = "Décaissements"
        ordering = ["-date_decaissement"]

    def __str__(self):
        return f"{self.numero} - {self.montant} ({self.beneficiaire or 'N/A'})"

    def clean(self):
        """
        - un décaissement ne se modifie pas après coup ;
        - montant strictement positif, motif obligatoire ;
        - uniquement sur une session OUVERTE et dans la limite de
          l'argent présent en caisse (solde théorique) ;
        - autorisé par une autre personne que celle qui décaisse, et
          jamais par un caissier (le caissier seul ne peut pas sortir
          d'argent sans validation, §9.1).
        """
        if self.pk is not None:
            raise ValidationError("Un décaissement enregistré ne peut pas être modifié.")
        exiger_positif(self.montant, "montant", "Le montant du décaissement")
        if not (self.motif or "").strip():
            raise ValidationError({"motif": "Le motif du décaissement est obligatoire."})
        if self.session_caisse_id:
            session = self.session_caisse
            if session.statut != StatutSession.OUVERTE:
                raise ValidationError({"session_caisse": "Cette session de caisse est clôturée : aucun décaissement possible."})
            disponible = session.calculer_solde_theorique()
            if self.montant > disponible:
                raise ValidationError({"montant": (
                    f"Montant supérieur à l'argent disponible en caisse ({disponible})."
                )})
        if self.autorise_par_id:
            if not self.autorise_par.is_active:
                raise ValidationError({"autorise_par": "Le compte de la personne qui autorise est désactivé."})
            if self.autorise_par.profil == Profil.CAISSIER and not self.autorise_par.is_superuser:
                raise ValidationError({"autorise_par": "Un caissier ne peut pas autoriser un décaissement."})
            if self.effectue_par_id and self.autorise_par_id == self.effectue_par_id:
                raise ValidationError({"autorise_par": "Le décaissement doit être autorisé par une autre personne que celle qui l'effectue."})

    def verifier_suppression(self):
        raise ValidationError("Un décaissement ne peut pas être supprimé.")

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("DEC")
        super().save(*args, **kwargs)
