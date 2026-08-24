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
