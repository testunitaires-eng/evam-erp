from django.db import models

# Create your models here.
"""
Module 9 - Reporting (cahier des charges mis à jour, §12).

Ce module ne stocke quasiment rien : il lit et agrège les données des
autres modules (règle §15 : "une information saisie ne doit pas être
ressaisie ailleurs"). La seule exception est RapportGenere, qui
conserve un instantané figé d'un rapport à une date donnée (§12.1,
rubrique "Rapports périodiques") - utile pour comparer un rapport
d'il y a un mois à la situation actuelle, ce qu'une vue en lecture
seule ne permettrait pas (les données sous-jacentes changent).
"""

from django.db import models
from apps.comptes.models import Utilisateur


class PeriodeRapport(models.TextChoices):
    JOURNALIER = "JOURNALIER", "Journalier"
    MENSUEL = "MENSUEL", "Mensuel"


class RapportGenere(models.Model):
    """Instantané figé d'un tableau de bord à une date donnée (§12.1)."""
    periode = models.CharField("Période", max_length=15, choices=PeriodeRapport.choices)
    date_rapport = models.DateField("Date du rapport")
    contenu = models.JSONField(
        "Contenu du rapport",
        help_text="Copie figée de la réponse du tableau de bord Direction à cette date.",
    )
    genere_par = models.ForeignKey(Utilisateur, verbose_name="Généré par", on_delete=models.PROTECT)
    date_generation = models.DateTimeField("Date de génération", auto_now_add=True)

    class Meta:
        verbose_name = "Rapport généré"
        verbose_name_plural = "Rapports générés"
        ordering = ["-date_rapport"]
        unique_together = ("periode", "date_rapport")

    def __str__(self):
        return f"Rapport {self.get_periode_display()} du {self.date_rapport}"