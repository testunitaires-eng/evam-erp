"""
Module 12 - Administration / Droits.

Ce module définit :
- Utilisateur : le compte de connexion, avec un "profil" métier unique
  (un des 11 acteurs identifiés dans le cahier des charges).
- MatriceDroit : la matrice de droits configurable par profil et par
  module (consulter / créer / modifier / valider / annuler / exporter /
  paramétrer), telle que décrite dans le cahier des charges.

Les autres applications importent PROFIL_CHOICES depuis ce fichier
pour restreindre leurs permissions (voir apps/comptes/permissions.py).
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Profil(models.TextChoices):
    """
    Les 12 acteurs de l'application (11 issus du cahier des charges +
    Responsable Achat, ajouté car le document décrit un module Achats
    complet - §6 - sans jamais nommer explicitement qui le pilote).
    Un utilisateur a un seul profil principal.
    """
    RESPONSABLE_PRODUCTION = "RESPONSABLE_PRODUCTION", "Responsable Production"
    AGENT_PRODUCTION = "AGENT_PRODUCTION", "Agent Production"
    MAGASINIER = "MAGASINIER", "Magasinier"
    RESPONSABLE_QUALITE = "RESPONSABLE_QUALITE", "Responsable Qualité"
    RESPONSABLE_ACHATS = "RESPONSABLE_ACHATS", "Responsable Achat"
    COMMERCIAL = "COMMERCIAL", "Commercial"
    CAISSIER = "CAISSIER", "Caissier"
    RESPONSABLE_DISTRIBUTION = "RESPONSABLE_DISTRIBUTION", "Responsable Distribution"
    CHAUFFEUR = "CHAUFFEUR", "Chauffeur / Livreur"
    COMPTABILITE_DAF = "COMPTABILITE_DAF", "Comptabilité / DAF"
    DIRECTION = "DIRECTION", "PDG / Direction"
    ADMIN_SI = "ADMIN_SI", "Administrateur SI"


class Utilisateur(AbstractUser):
    """
    Compte utilisateur de l'application.

    Hérite du modèle utilisateur standard de Django, qui fournit déjà
    `is_active` : ce champ est LE mécanisme réel d'activation/
    désactivation. SimpleJWT vérifie `is_active` à CHAQUE requête (pas
    seulement à la connexion), donc désactiver un compte le coupe
    immédiatement, même s'il a déjà un jeton JWT valide en cours.

    (Une ancienne version de ce modèle avait un champ `actif` distinct
    qui n'était jamais vérifié nulle part - un compte "désactivé" via
    ce champ pouvait donc continuer à se connecter normalement. Ce
    champ a été supprimé pour ne garder qu'un seul mécanisme, le bon.)
    """
    profil = models.CharField(
        "Profil",
        max_length=32,
        choices=Profil.choices,
        help_text="Rôle métier de l'utilisateur dans l'application. "
                   "Détermine ses droits d'accès via la matrice de droits.",
    )
    telephone = models.CharField("Téléphone", max_length=30, blank=True)
    date_creation = models.DateTimeField("Date de création", auto_now_add=True)
    desactive_par = models.ForeignKey(
        "self", verbose_name="Désactivé par", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="comptes_desactives",
        help_text="Traçabilité : qui a désactivé ce compte, le cas échéant.",
    )
    date_desactivation = models.DateTimeField("Date de désactivation", null=True, blank=True)

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        etat = "actif" if self.is_active else "désactivé"
        return f"{self.get_full_name() or self.username} ({self.get_profil_display()}, {etat})"

    def desactiver(self, par_utilisateur):
        """Désactive le compte. Effectif immédiatement sur toute requête suivante."""
        from django.utils import timezone
        self.is_active = False
        self.desactive_par = par_utilisateur
        self.date_desactivation = timezone.now()
        self.save()

    def activer(self):
        """Réactive le compte."""
        self.is_active = True
        self.desactive_par = None
        self.date_desactivation = None
        self.save()


class Module(models.TextChoices):
    """Liste des modules de l'application, pour la matrice de droits."""
    ACCUEIL = "ACCUEIL", "Accueil / Tableau de bord"
    REFERENTIEL = "REFERENTIEL", "Référentiel"
    ACHATS = "ACHATS", "Achats"
    STOCKS = "STOCKS", "Stocks"
    PRODUCTION = "PRODUCTION", "Production"
    QUALITE = "QUALITE", "Qualité / Traçabilité"
    COMMERCIAL = "COMMERCIAL", "Gestion commerciale"
    CAISSE = "CAISSE", "Caisse"
    DISTRIBUTION = "DISTRIBUTION", "Distribution / Logistique"
    COUTS = "COUTS", "Coûts & Rentabilité"
    COMPTABILITE = "COMPTABILITE", "Pilotage / Comptabilité"
    ADMINISTRATION = "ADMINISTRATION", "Administration / Droits"


class MatriceDroit(models.Model):
    """
    Une ligne de la matrice de droits : pour un profil donné et un
    module donné, quelles actions sont autorisées.

    Exemple métier du cahier des charges : le Magasinier ne peut PAS
    créer/modifier une fiche technique -> une ligne
    (MAGASINIER, REFERENTIEL, peut_modifier=False) formalise cette règle.

    Cette table permet à l'Administrateur SI d'ajuster les droits
    sans toucher au code (voir §Module 12 du cahier des charges).
    """
    profil = models.CharField("Profil", max_length=32, choices=Profil.choices)
    module = models.CharField("Module", max_length=32, choices=Module.choices)

    peut_consulter = models.BooleanField("Peut consulter", default=False)
    peut_creer = models.BooleanField("Peut créer", default=False)
    peut_modifier = models.BooleanField("Peut modifier", default=False)
    peut_valider = models.BooleanField("Peut valider", default=False)
    peut_annuler = models.BooleanField("Peut annuler", default=False)
    peut_exporter = models.BooleanField("Peut exporter", default=False)
    peut_parametrer = models.BooleanField("Peut paramétrer", default=False)

    class Meta:
        verbose_name = "Droit d'accès"
        verbose_name_plural = "Matrice des droits d'accès"
        unique_together = ("profil", "module")
        ordering = ["profil", "module"]

    def __str__(self):
        return f"{self.get_profil_display()} / {self.get_module_display()}"


class JournalAction(models.Model):
    """
    Traçabilité systématique des actions importantes (voir cahier des
    charges §16.1) : qui a fait quoi, quand, sur quel document, avec
    quelle valeur avant/après et pour quel motif.

    Ce modèle est générique et peut être utilisé par n'importe quelle
    application via un simple appel à JournalAction.objects.create(...).
    Rien n'est supprimé dans l'application : on trace, on annule ou on
    fait une contre-opération, jamais une suppression silencieuse.
    """
    utilisateur = models.ForeignKey(
        Utilisateur, verbose_name="Utilisateur", on_delete=models.PROTECT
    )
    module = models.CharField("Module", max_length=32, choices=Module.choices)
    action = models.CharField(
        "Action", max_length=100,
        help_text="Ex : 'création OF', 'libération lot', 'annulation commande'",
    )
    document_type = models.CharField("Type de document", max_length=100, blank=True)
    document_id = models.CharField("Référence du document", max_length=100, blank=True)
    ancienne_valeur = models.TextField("Ancienne valeur", blank=True)
    nouvelle_valeur = models.TextField("Nouvelle valeur", blank=True)
    motif = models.TextField("Motif", blank=True)
    date_action = models.DateTimeField("Date de l'action", auto_now_add=True)

    class Meta:
        verbose_name = "Action journalisée"
        verbose_name_plural = "Journal des actions"
        ordering = ["-date_action"]

    def __str__(self):
        return f"[{self.date_action:%Y-%m-%d %H:%M}] {self.utilisateur} - {self.action}"
