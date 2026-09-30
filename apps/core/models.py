"""
Utilitaires transverses partagés par tous les modules métier.

SequenceNumerotation implémente la règle du cahier des charges §16.1 :
"Numérotation automatique unique pour chaque pièce (OF, lot, commande,
facture, BL, encaissement)". Chaque module appelle
generer_numero(prefixe) pour obtenir un numéro garanti unique,
séquentiel et jamais réutilisé.
"""

from django.db import models, transaction


class SequenceNumerotation(models.Model):
    """
    Compteur par préfixe (ex: 'OF', 'LOT', 'CMD', 'FACT', 'BL', 'ENC').
    Une ligne par type de document.
    """
    prefixe = models.CharField("Préfixe", max_length=10, unique=True)
    dernier_numero = models.PositiveIntegerField("Dernier numéro utilisé", default=0)

    class Meta:
        verbose_name = "Séquence de numérotation"
        verbose_name_plural = "Séquences de numérotation"

    def __str__(self):
        return f"{self.prefixe} -> {self.dernier_numero}"


def generer_numero(prefixe: str, largeur: int = 6) -> str:
    """
    Génère un numéro unique et séquentiel du type 'OF-000123'.

    Utilise select_for_update() dans une transaction pour garantir
    l'unicité même en cas d'accès concurrents (deux utilisateurs qui
    créent un document en même temps).

    Exemple :
        numero_of = generer_numero("OF")       # -> "OF-000001"
        numero_lot = generer_numero("LOT")     # -> "LOT-000001"
    """
    with transaction.atomic():
        sequence, _ = SequenceNumerotation.objects.select_for_update().get_or_create(
            prefixe=prefixe
        )
        sequence.dernier_numero += 1
        sequence.save()
        return f"{prefixe}-{str(sequence.dernier_numero).zfill(largeur)}"


def generer_code_unique(modele, prefixe, champ="code", largeur=6):
    """
    Codification automatique des fiches de référence (articles, clients,
    fournisseurs...) : aucun code n'est saisi par l'utilisateur.
    Comme generer_numero, mais saute les codes déjà pris (ex : un code
    saisi à la main avant l'automatisation, qui aurait le même format).
    """
    while True:
        code = generer_numero(prefixe, largeur)
        if not modele._default_manager.filter(**{champ: code}).exists():
            return code



class Historique(models.Model):
    """
    Une ligne de l'historique d'un document (création, changement de
    statut). Écrite automatiquement (apps/core/historique.py), jamais
    saisie ni modifiée.
    """
    content_type = models.ForeignKey(
        "contenttypes.ContentType", verbose_name="Type de document", on_delete=models.CASCADE,
    )
    objet_id = models.PositiveBigIntegerField("Identifiant du document")
    reference = models.CharField("Référence", max_length=50, blank=True)
    action = models.CharField("Action", max_length=50)
    ancien_statut = models.CharField("Ancien statut", max_length=60, blank=True)
    nouveau_statut = models.CharField("Nouveau statut", max_length=60, blank=True)
    utilisateur = models.ForeignKey(
        "comptes.Utilisateur", verbose_name="Par", on_delete=models.PROTECT, null=True, blank=True,
    )
    date = models.DateTimeField("Date", auto_now_add=True)

    class Meta:
        verbose_name = "Historique de document"
        verbose_name_plural = "Historique des documents"
        ordering = ["date", "pk"]
        indexes = [models.Index(fields=["content_type", "objet_id"])]

    def __str__(self):
        return f"{self.reference} : {self.action} ({self.ancien_statut} -> {self.nouveau_statut})"


class Notification(models.Model):
    """
    Notification (cloche de la barre du haut) : chaque notification
    ouvre directement le tiroir du document concerné (type + id).
    Créée automatiquement (apps/core/notifications.py), jamais saisie.
    """
    destinataire = models.ForeignKey(
        "comptes.Utilisateur", verbose_name="Destinataire", on_delete=models.CASCADE, related_name="notifications",
    )
    titre = models.CharField("Titre", max_length=150)
    message = models.CharField("Message", max_length=500, blank=True)
    type_document = models.CharField("Type de document", max_length=60, blank=True, help_text="Ex : caisse.decaissement")
    document_id = models.PositiveBigIntegerField("Identifiant du document", null=True, blank=True)
    reference = models.CharField("Référence", max_length=50, blank=True)
    lue = models.BooleanField("Lue", default=False)
    date = models.DateTimeField("Date", auto_now_add=True)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-date", "-pk"]
        indexes = [models.Index(fields=["destinataire", "lue"])]

    def __str__(self):
        return f"{self.destinataire} : {self.titre}"
