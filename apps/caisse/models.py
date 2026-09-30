"""
Module 8 - Caisse.

Le Caissier "ne peut pas modifier commande, prix, stock, ni supprimer
un écart — il doit le justifier". Ces règles sont appliquées via les
permissions (voir views.py) et via l'absence de champs modifiables
directement sur la commande/le stock depuis ce module.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.comptes.models import Utilisateur, Profil
from apps.commercial.models import Facture, StatutFacture
from apps.core.models import generer_numero
from apps.core.validation import (
    ValidationAvantEnregistrement, exiger_positif, valeur_en_base, convertir_decimal, verifier_transition,
)


# Seules ces fonctions peuvent autoriser une sortie d'argent (décaissement).
PROFILS_AUTORISANT_DECAISSEMENT = (Profil.DIRECTION, Profil.COMPTABILITE_DAF)


def nom_utilisateur(utilisateur):
    """Nom lisible pour les journaux (nom complet, sinon identifiant)."""
    if utilisateur is None:
        return None
    return utilisateur.get_full_name() or utilisateur.username


class Caisse(ValidationAvantEnregistrement, models.Model):
    """
    Deux sortes de caisses :
    - la CAISSE PRINCIPALE (une seule, créée automatiquement par le
      système) : aucune session ne s'y ouvre ; elle consolide le solde
      de toutes les caisses et le journal de toutes les opérations
      (qui a encaissé/décaissé quoi, où, quand) ;
    - les caisses des caissiers, créées par l'Administrateur SI, chacune
      affectée à UN caissier, qui y ouvre et clôture ses sessions.
    """
    nom = models.CharField("Nom de la caisse", max_length=100)
    emplacement = models.CharField("Emplacement", max_length=150, blank=True)
    actif = models.BooleanField("Active", default=True)
    est_principale = models.BooleanField(
        "Caisse principale", default=False, editable=False,
        help_text="Caisse de consolidation créée par le système (une seule).",
    )
    caissier = models.OneToOneField(
        Utilisateur, verbose_name="Caissier affecté", on_delete=models.PROTECT,
        null=True, blank=True, related_name="caisse_affectee",
        limit_choices_to={"profil": Profil.CAISSIER},
        help_text="Le caissier qui ouvre et clôture ses sessions sur cette caisse (un caissier = une caisse).",
    )

    class Meta:
        verbose_name = "Caisse"
        verbose_name_plural = "Caisses"
        constraints = [
            models.UniqueConstraint(
                fields=["est_principale"], condition=models.Q(est_principale=True),
                name="une_seule_caisse_principale",
            ),
        ]

    def __str__(self):
        return self.nom

    @classmethod
    def principale(cls):
        return cls.objects.filter(est_principale=True).first()

    def clean(self):
        self.nom = (self.nom or "").strip()
        if not self.nom:
            raise ValidationError({"nom": "Le nom de la caisse est obligatoire."})
        if Caisse.objects.filter(nom__iexact=self.nom).exclude(pk=self.pk).exists():
            raise ValidationError({"nom": f"Une caisse nommée « {self.nom} » existe déjà."})
        if self.est_principale:
            if self.caissier_id:
                raise ValidationError({"caissier": (
                    "La caisse principale consolide toutes les caisses : aucun caissier ne lui est affecté."
                )})
            if not self.actif:
                raise ValidationError({"actif": "La caisse principale ne peut pas être désactivée."})
        elif self.caissier_id:
            caissier = self.caissier
            if caissier.profil != Profil.CAISSIER:
                raise ValidationError({"caissier": f"{caissier} n'a pas le profil Caissier."})
            if not caissier.is_active:
                raise ValidationError({"caissier": f"Le compte de {caissier} est désactivé."})
        if self.pk and self.session_ouverte() is not None:
            if valeur_en_base(self, "caissier") != self.caissier_id:
                raise ValidationError({"caissier": "Une session est ouverte sur cette caisse : clôturez-la avant de changer de caissier."})
            if not self.actif:
                raise ValidationError({"actif": "Une session est ouverte sur cette caisse : clôturez-la avant de la désactiver."})

    def verifier_suppression(self):
        if self.est_principale:
            raise ValidationError("La caisse principale ne peut pas être supprimée.")
        if self.sessions.exists():
            raise ValidationError("Cette caisse a un historique de sessions : désactivez-la plutôt que de la supprimer.")

    def session_ouverte(self):
        return self.sessions.filter(statut=StatutSession.OUVERTE).first() if self.pk else None

    def solde_propre(self):
        """
        Argent de CETTE caisse : solde théorique de la session ouverte, ou,
        caisse fermée, solde COMPTÉ de la dernière clôture (l'argent
        réellement en caisse, repris à la prochaine ouverture). 0 si
        jamais ouverte.
        """
        session = self.session_ouverte()
        if session is not None:
            return session.calculer_solde_theorique()
        derniere = self.sessions.filter(statut=StatutSession.CLOTUREE).order_by("-date_cloture", "-pk").first()
        return derniere.solde_compte_cloture if derniere else Decimal("0")

    @property
    def solde_actuel(self):
        """Caisse principale : total de toutes les caisses. Autre caisse : son propre solde."""
        if self.est_principale:
            return sum((caisse.solde_propre() for caisse in Caisse.objects.all()), Decimal("0"))
        return self.solde_propre()

    def operations(self, date_debut=None, date_fin=None, caissier=None):
        """
        Journal des entrées/sorties d'argent (traçabilité) : pour la
        caisse principale, toutes les caisses ; sinon cette caisse seule.
        Chaque ligne : type, numéro, date/heure, montant, caisse, caissier, détail.
        """
        encaissements = Encaissement.objects.select_related(
            "session_caisse__caisse", "session_caisse__caissier", "encaisse_par", "facture__client",
        )
        decaissements = Decaissement.objects.filter(statut=StatutDecaissement.EFFECTUE).select_related(
            "session_caisse__caisse", "effectue_par", "autorise_par",
        )
        if not self.est_principale:
            encaissements = encaissements.filter(session_caisse__caisse=self)
            decaissements = decaissements.filter(session_caisse__caisse=self)
        if date_debut:
            encaissements = encaissements.filter(date_encaissement__date__gte=date_debut)
            decaissements = decaissements.filter(date_execution__date__gte=date_debut)
        if date_fin:
            encaissements = encaissements.filter(date_encaissement__date__lte=date_fin)
            decaissements = decaissements.filter(date_execution__date__lte=date_fin)
        if caissier:
            encaissements = encaissements.filter(session_caisse__caissier_id=caissier)
            decaissements = decaissements.filter(session_caisse__caissier_id=caissier)

        lignes = [
            {
                "type": "ENCAISSEMENT", "numero": e.numero, "date": e.date_encaissement,
                "montant": e.montant, "caisse": e.session_caisse.caisse.nom,
                "caissier": nom_utilisateur(e.encaisse_par or e.session_caisse.caissier),
                "caissier_id": (e.encaisse_par or e.session_caisse.caissier).pk,
                "session": e.session_caisse_id, "mode_paiement": e.mode_paiement,
                "detail": f"Facture {e.facture.numero} - {e.facture.client.nom}",
            }
            for e in encaissements
        ] + [
            {
                "type": "DECAISSEMENT", "numero": d.numero, "date": d.date_execution or d.date_decaissement,
                "montant": -d.montant, "caisse": d.session_caisse.caisse.nom,
                "caissier": nom_utilisateur(d.effectue_par), "caissier_id": d.effectue_par_id,
                "session": d.session_caisse_id, "mode_paiement": None,
                "detail": f"{d.motif} (autorisé par {nom_utilisateur(d.autorise_par)}"
                          + (f", bénéficiaire {d.beneficiaire})" if d.beneficiaire else ")"),
            }
            for d in decaissements
        ]
        return sorted(lignes, key=lambda ligne: ligne["date"], reverse=True)


class StatutSession(models.TextChoices):
    OUVERTE = "OUVERTE", "Ouverte"
    CLOTUREE = "CLOTUREE", "Clôturée"


class SessionCaisse(ValidationAvantEnregistrement, models.Model):
    """
    Une session = une ouverture de caisse par un caissier jusqu'à sa
    clôture. L'écart entre solde théorique et solde réel compté est
    calculé automatiquement à la clôture (§11.3).
    """
    caisse = models.ForeignKey(Caisse, verbose_name="Caisse", on_delete=models.PROTECT, related_name="sessions")
    caissier = models.ForeignKey(Utilisateur, verbose_name="Caissier", on_delete=models.PROTECT)
    solde_ouverture = models.DecimalField(
        "Solde d'ouverture", max_digits=14, decimal_places=2,
        help_text="Automatique : 0 à la première ouverture de la caisse, puis le solde "
                  "COMPTÉ de la clôture précédente (l'argent réellement en caisse).",
    )
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

    def solde_ouverture_attendu(self):
        """
        Report : solde COMPTÉ de la dernière session clôturée de la caisse
        (0 à la première ouverture). On repart de l'argent réellement
        présent : un écart déjà justifié la veille ne se reporte pas sur
        les jours suivants (il reste tracé dans EcartCaisse).
        """
        derniere = (
            SessionCaisse.objects.filter(caisse_id=self.caisse_id, statut=StatutSession.CLOTUREE)
            .exclude(pk=self.pk).order_by("-date_cloture", "-pk").first()
        )
        return derniere.solde_compte_cloture if derniere else Decimal("0")

    def clean(self):
        """
        - on n'ouvre pas de session sur la caisse principale (consolidation) ;
        - le caissier ouvre sa session sur SA caisse (celle qui lui est
          affectée), active, une seule session ouverte à la fois ;
        - solde d'ouverture automatique (voir solde_ouverture_attendu),
          jamais saisi ;
        - une session clôturée est figée ; caisse, caissier et solde
          d'ouverture ne changent plus.
        """
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut == StatutSession.CLOTUREE:
            raise ValidationError("Cette session de caisse est clôturée : elle ne peut plus être modifiée.")
        if ancien_statut is None:
            if self.statut != StatutSession.OUVERTE:
                raise ValidationError({"statut": "Une session de caisse est toujours créée ouverte."})
            if self.caisse_id:
                caisse = self.caisse
                if caisse.est_principale:
                    raise ValidationError({"caisse": (
                        "La caisse principale consolide les caisses des caissiers : "
                        "on n'y ouvre pas de session. Ouvrez la session sur votre caisse."
                    )})
                if not caisse.actif:
                    raise ValidationError({"caisse": f"La caisse « {caisse.nom} » est inactive."})
                if caisse.caissier_id is None:
                    raise ValidationError({"caisse": f"Aucun caissier n'est affecté à la caisse « {caisse.nom} »."})
                if self.caissier_id and self.caissier_id != caisse.caissier_id:
                    raise ValidationError({"caisse": (
                        f"La caisse « {caisse.nom} » est affectée à {caisse.caissier} : "
                        "vous ne pouvez ouvrir une session que sur votre propre caisse."
                    )})
                if SessionCaisse.objects.filter(caisse_id=self.caisse_id, statut=StatutSession.OUVERTE).exists():
                    raise ValidationError({"caisse": (
                        f"La caisse « {caisse.nom} » a déjà une session ouverte : "
                        "clôturez-la avant d'en ouvrir une nouvelle."
                    )})
                self.solde_ouverture = self.solde_ouverture_attendu()
        else:
            for champ in ("caisse", "caissier"):
                if valeur_en_base(self, champ) != getattr(self, f"{champ}_id"):
                    raise ValidationError({champ: "Ce champ ne peut pas être changé après l'ouverture."})
            if valeur_en_base(self, "solde_ouverture") != self.solde_ouverture:
                raise ValidationError({"solde_ouverture": "Le solde d'ouverture est automatique : il ne se modifie pas."})

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

    @property
    def solde_theorique_actuel(self):
        """Pendant la session : calculé en direct. Après clôture : le théorique figé."""
        if self.statut == StatutSession.OUVERTE:
            return self.calculer_solde_theorique() if self.pk else self.solde_ouverture
        return self.solde_theorique_cloture

    def calculer_solde_theorique(self):
        """
        §9.2 : solde théorique = ouverture + encaissements - décaissements.
        Utilisé par défaut à la clôture si aucun solde_theorique n'est
        fourni explicitement.
        """
        from django.db.models import Sum
        total_encaissements = self.encaissements.aggregate(total=Sum("montant"))["total"] or 0
        total_decaissements = self.decaissements.filter(
            statut=StatutDecaissement.EFFECTUE,
        ).aggregate(total=Sum("montant"))["total"] or 0
        return self.solde_ouverture + total_encaissements - total_decaissements

    @transaction.atomic
    def cloturer(self, solde_compte, justification=None):
        """
        Clôture la journée de caisse :
        - solde théorique TOUJOURS calculé par le système (ouverture +
          encaissements - décaissements), jamais saisi ;
        - solde compté = l'argent que le caissier a réellement en main (saisi) ;
        - s'il y a un écart, la justification est OBLIGATOIRE ici, AVANT
          la clôture : sans elle, rien n'est clôturé. L'écart justifié
          est enregistré (EcartCaisse) pour contrôle par la Comptabilité/DAF.
        Lève ValueError sinon.
        """
        from django.utils import timezone
        if self.statut != StatutSession.OUVERTE:
            raise ValueError("Cette session est déjà clôturée.")
        solde_compte = convertir_decimal(solde_compte, "Le solde compté (solde_compte)", strict=False)
        solde_theorique = self.calculer_solde_theorique()
        ecart = solde_compte - solde_theorique
        justification = (justification or "").strip()
        if ecart and not justification:
            raise ValueError(
                f"Écart de {ecart} FCFA entre le solde compté ({solde_compte}) et le solde "
                f"théorique ({solde_theorique}) : la justification est obligatoire pour clôturer."
            )
        self.solde_theorique_cloture = solde_theorique
        self.solde_compte_cloture = solde_compte
        self.statut = StatutSession.CLOTUREE
        self.date_cloture = timezone.now()
        self.save()
        if ecart:
            EcartCaisse.objects.create(session_caisse=self, justification=justification)
            from apps.comptabilite.anomalies import controler_ecart_caisse
            controler_ecart_caisse(self)

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
    encaisse_par = models.ForeignKey(
        Utilisateur, verbose_name="Encaissé par", on_delete=models.PROTECT,
        null=True, blank=True, related_name="encaissements_effectues",
        help_text="Traçabilité : le caissier qui a encaissé (renseigné automatiquement).",
    )
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
        if self.session_caisse_id and self.encaisse_par_id and self.encaisse_par_id != self.session_caisse.caissier_id:
            raise ValidationError({"session_caisse": "Seul le caissier de cette session peut y encaisser (sa propre caisse)."})
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
            creation = self._state.adding
            if not self.numero:
                self.numero = generer_numero("ENC")
            super().save(*args, **kwargs)
            self.facture.mettre_a_jour_statut_paiement()
            if creation:
                from apps.comptabilite.ecritures import ecrire_encaissement
                ecrire_encaissement(self)


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
        - créé à la clôture de la session (SessionCaisse.cloturer), avec
          sa justification : le montant est repris de la session (pas saisi) ;
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






class StatutDecaissement(models.TextChoices):
    EN_ATTENTE = "EN_ATTENTE", "En attente d'autorisation"
    AUTORISE = "AUTORISE", "Autorisé"
    REFUSE = "REFUSE", "Refusé"
    EFFECTUE = "EFFECTUE", "Effectué"


class Decaissement(ValidationAvantEnregistrement, models.Model):
    """
    §9.1/§9.2 : sortie de caisse, distincte d'un encaissement, en 3 temps :
    1. le caissier fait la DEMANDE (montant, motif, bénéficiaire) ;
    2. la Direction ou la Comptabilité/DAF l'AUTORISE ou la REFUSE (motif) ;
    3. le caissier EFFECTUE la sortie d'argent (seulement si autorisée,
       sur une session ouverte, dans la limite de l'argent en caisse).
    Seuls les décaissements EFFECTUÉS diminuent le solde de la caisse.
    """
    TRANSITIONS = {
        StatutDecaissement.EN_ATTENTE: {StatutDecaissement.AUTORISE, StatutDecaissement.REFUSE},
        StatutDecaissement.AUTORISE: {StatutDecaissement.EFFECTUE},
    }
    CHAMPS_FIGES = ("montant", "motif", "beneficiaire", "effectue_par")

    numero = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    session_caisse = models.ForeignKey(
        SessionCaisse, verbose_name="Session de caisse", on_delete=models.PROTECT,
        related_name="decaissements",
    )
    montant = models.DecimalField("Montant", max_digits=14, decimal_places=2)
    motif = models.TextField("Motif")
    beneficiaire = models.CharField("Bénéficiaire", max_length=200, blank=True)
    statut = models.CharField(
        "Statut", max_length=15, choices=StatutDecaissement.choices, default=StatutDecaissement.EN_ATTENTE,
    )
    autorise_par = models.ForeignKey(
        Utilisateur, verbose_name="Autorisé / refusé par", on_delete=models.PROTECT,
        null=True, blank=True, related_name="decaissements_autorises",
        limit_choices_to={"profil__in": PROFILS_AUTORISANT_DECAISSEMENT, "is_active": True},
        help_text="Direction ou Comptabilité/DAF : renseigné par l'action Autoriser / Refuser.",
    )
    date_autorisation = models.DateTimeField("Date d'autorisation / de refus", null=True, blank=True)
    motif_refus = models.TextField("Motif du refus", blank=True)
    effectue_par = models.ForeignKey(
        Utilisateur, verbose_name="Caissier", on_delete=models.PROTECT,
        related_name="decaissements_effectues",
    )
    date_decaissement = models.DateTimeField("Date de la demande", auto_now_add=True)
    date_execution = models.DateTimeField("Date de sortie d'argent", null=True, blank=True)

    class Meta:
        verbose_name = "Décaissement"
        verbose_name_plural = "Décaissements"
        ordering = ["-date_decaissement"]

    def __str__(self):
        return f"{self.numero} - {self.montant} ({self.beneficiaire or 'N/A'})"

    def clean(self):
        """
        - montant > 0, motif obligatoire, demande faite par le caissier de
          la session, sur une session ouverte ;
        - statut : En attente -> Autorisé / Refusé ; Autorisé -> Effectué.
          Refusé et Effectué sont définitifs ; montant, motif, bénéficiaire
          et caissier ne changent plus après la demande ;
        - autorisation uniquement par la Direction ou la Comptabilité/DAF,
          jamais par le caissier lui-même ;
        - sortie d'argent : session ouverte et montant <= argent en caisse.
        """
        exiger_positif(self.montant, "montant", "Le montant du décaissement")
        if not (self.motif or "").strip():
            raise ValidationError({"motif": "Le motif du décaissement est obligatoire."})
        ancien_statut = valeur_en_base(self, "statut")
        if ancien_statut in (StatutDecaissement.REFUSE, StatutDecaissement.EFFECTUE):
            raise ValidationError(
                f"Ce décaissement est {dict(StatutDecaissement.choices)[ancien_statut].lower()} : il ne peut plus être modifié."
            )
        verifier_transition(
            ancien_statut, self.statut, self.TRANSITIONS, "statut du décaissement",
            initial=StatutDecaissement.EN_ATTENTE,
        )
        if self.pk is not None:
            for champ in self.CHAMPS_FIGES:
                attribut = f"{champ}_id" if champ == "effectue_par" else champ
                if valeur_en_base(self, champ) != getattr(self, attribut):
                    raise ValidationError({champ: "Ce champ ne peut plus être modifié après la demande."})

        if self.session_caisse_id:
            session = self.session_caisse
            if self.effectue_par_id and self.effectue_par_id != session.caissier_id:
                raise ValidationError({"session_caisse": "Seul le caissier de cette session peut y décaisser (sa propre caisse)."})
            if ancien_statut is None and session.statut != StatutSession.OUVERTE:
                raise ValidationError({"session_caisse": "Cette session de caisse est clôturée : aucune demande de décaissement possible."})
            if self.statut == StatutDecaissement.EFFECTUE and ancien_statut != StatutDecaissement.EFFECTUE:
                if session.statut != StatutSession.OUVERTE:
                    raise ValidationError({"session_caisse": "Ouvrez votre session de caisse pour effectuer ce décaissement."})
                disponible = session.calculer_solde_theorique()
                if self.montant > disponible:
                    raise ValidationError({"montant": f"Montant supérieur à l'argent disponible en caisse ({disponible})."})

        if self.statut in (StatutDecaissement.AUTORISE, StatutDecaissement.REFUSE) and ancien_statut == StatutDecaissement.EN_ATTENTE:
            if not self.autorise_par_id:
                raise ValidationError({"autorise_par": "La personne qui autorise ou refuse doit être renseignée."})
            if self.statut == StatutDecaissement.REFUSE and not (self.motif_refus or "").strip():
                raise ValidationError({"motif_refus": "Le motif du refus est obligatoire."})
        if self.autorise_par_id:
            if not self.autorise_par.is_active:
                raise ValidationError({"autorise_par": "Le compte de la personne qui autorise est désactivé."})
            if self.autorise_par.profil not in PROFILS_AUTORISANT_DECAISSEMENT and not self.autorise_par.is_superuser:
                raise ValidationError({"autorise_par": (
                    "Un décaissement ne peut être autorisé que par la Direction ou la Comptabilité/DAF."
                )})
            if self.effectue_par_id and self.autorise_par_id == self.effectue_par_id:
                raise ValidationError({"autorise_par": "Le décaissement doit être autorisé par une autre personne que celle qui l'effectue."})

    def verifier_suppression(self):
        raise ValidationError("Un décaissement ne peut pas être supprimé (refusez la demande si elle n'a pas lieu d'être).")

    def _decider(self, utilisateur, statut, motif_refus=""):
        from django.utils import timezone
        if self.statut != StatutDecaissement.EN_ATTENTE:
            raise ValueError(f"Cette demande est déjà « {self.get_statut_display()} ».")
        self.statut = statut
        self.autorise_par = utilisateur
        self.date_autorisation = timezone.now()
        self.motif_refus = (motif_refus or "").strip()
        self.save()

    def autoriser(self, utilisateur):
        """Direction ou Comptabilité/DAF : autorise la sortie d'argent."""
        self._decider(utilisateur, StatutDecaissement.AUTORISE)

    def refuser(self, utilisateur, motif):
        """Direction ou Comptabilité/DAF : refuse, avec motif obligatoire."""
        if not (motif or "").strip():
            raise ValueError("Le motif du refus est obligatoire.")
        self._decider(utilisateur, StatutDecaissement.REFUSE, motif)

    @transaction.atomic
    def effectuer(self, utilisateur):
        """
        Le caissier sort l'argent. Si la session de la demande a été
        clôturée entre-temps, la sortie est rattachée à la session
        OUVERTE de sa caisse (le jour où l'argent sort réellement).
        """
        from django.utils import timezone
        if self.statut != StatutDecaissement.AUTORISE:
            raise ValueError(
                f"Ce décaissement est « {self.get_statut_display()} » : seul un décaissement autorisé peut être effectué."
            )
        if utilisateur.pk != self.effectue_par_id and not utilisateur.is_superuser:
            raise ValueError("Seul le caissier qui a fait la demande peut effectuer ce décaissement.")
        if self.session_caisse.statut != StatutSession.OUVERTE:
            session = self.session_caisse.caisse.session_ouverte()
            if session is None:
                raise ValueError("Ouvrez votre session de caisse pour effectuer ce décaissement.")
            self.session_caisse = session
        self.statut = StatutDecaissement.EFFECTUE
        self.date_execution = timezone.now()
        self.save()
        from apps.comptabilite.ecritures import ecrire_decaissement
        ecrire_decaissement(self)

    def save(self, *args, **kwargs):
        if not self.numero:
            self.numero = generer_numero("DEC")
        super().save(*args, **kwargs)
