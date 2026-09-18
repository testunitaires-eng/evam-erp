# """
# Remplit la matrice fiscale avec les 4 codes fiscaux décrits dans le
# document "Matrice_fiscale_par_produit_EVAM" (§2 et §9).

# À lancer UNE FOIS après la migration :
#     python manage.py initialiser_matrice_fiscale

# Le code EV-FISC-EAU-EXO est créé avec sa réserve documentée
# ("qualification à confirmer") : à ADAPTER manuellement (ou via l'admin)
# le jour où la qualification "eau minérale produite au Congo" est
# officiellement validée ou refusée.
# """

# from django.core.management.base import BaseCommand
# from apps.fiscalite.models import CodeFiscal


# CODES_FISCAUX = [
#     dict(
#         code="EV-FISC-EAU-EXO",
#         famille_fiscale="Eau minérale produite au Congo",
#         exonere=True, taux_tva=0, taux_centimes_additionnels=0, taux_accise=0,
#         sfec_actif=True,
#         situation="Qualification \"eau minérale\" EVAM à confirmer officiellement. "
#                   "Si la qualification n'est pas retenue, rattacher les articles "
#                   "concernés à EV-FISC-EAU-18 à la place.",
#     ),
#     dict(
#         code="EV-FISC-EAU-18",
#         famille_fiscale="Eau ne bénéficiant pas de l'exonération",
#         exonere=False, taux_tva=18, taux_centimes_additionnels=5, taux_accise=0,
#         sfec_actif=True,
#         situation="Code de secours, à utiliser si EV-FISC-EAU-EXO n'est pas confirmé.",
#     ),
#     dict(
#         code="EV-FISC-JUS-10",
#         famille_fiscale="Jus EVAM sucré/aromatisé",
#         exonere=False, taux_tva=18, taux_centimes_additionnels=5, taux_accise=10,
#         sfec_actif=True,
#         situation="Règle à retenir pour toutes les recettes de jus décrites "
#                   "(eau traitée + sucre + arôme/colorant).",
#     ),
#     dict(
#         code="EV-FISC-YAO-18",
#         famille_fiscale="Yaourt",
#         exonere=False, taux_tva=18, taux_centimes_additionnels=5, taux_accise=0,
#         sfec_actif=True,
#         situation="Règle actuelle à retenir pour tous les yaourts.",
#     ),
# ]


# class Command(BaseCommand):
#     help = "Initialise la matrice fiscale avec les 4 codes fiscaux du document de référence."

#     def handle(self, *args, **options):
#         crees = 0
#         for donnees in CODES_FISCAUX:
#             _, cree = CodeFiscal.objects.get_or_create(
#                 code=donnees["code"], defaults=donnees,
#             )
#             if cree:
#                 crees += 1
#                 self.stdout.write(self.style.SUCCESS(f"  + {donnees['code']}"))
#             else:
#                 self.stdout.write(f"  - {donnees['code']} existe déjà, ignoré")
#         self.stdout.write(self.style.SUCCESS(f"\nTerminé : {crees} codes fiscaux créés."))



"""
Remplit la matrice fiscale avec les 4 codes fiscaux décrits dans le
document "Matrice_fiscale_par_produit_EVAM" (§2 et §9), ainsi que les
4 familles fiscales (liste déroulante) qu'ils utilisent.

À lancer UNE FOIS après la migration :
    python manage.py initialiser_matrice_fiscale

Le code EV-FISC-EAU-EXO est créé avec sa réserve documentée
("qualification à confirmer") : à ADAPTER manuellement (ou via l'admin)
le jour où la qualification "eau minérale produite au Congo" est
officiellement validée ou refusée.
"""

from django.core.management.base import BaseCommand
from apps.fiscalite.models import CodeFiscal, FamilleFiscale


CODES_FISCAUX = [
    dict(
        code="EV-FISC-EAU-EXO",
        famille_fiscale="Eau minérale produite au Congo",
        exonere=True, taux_tva=0, taux_centimes_additionnels=0, taux_accise=0,
        sfec_actif=True,
        situation="Qualification \"eau minérale\" EVAM à confirmer officiellement. "
                  "Si la qualification n'est pas retenue, rattacher les articles "
                  "concernés à EV-FISC-EAU-18 à la place.",
    ),
    dict(
        code="EV-FISC-EAU-18",
        famille_fiscale="Eau ne bénéficiant pas de l'exonération",
        exonere=False, taux_tva=18, taux_centimes_additionnels=5, taux_accise=0,
        sfec_actif=True,
        situation="Code de secours, à utiliser si EV-FISC-EAU-EXO n'est pas confirmé.",
    ),
    dict(
        code="EV-FISC-JUS-10",
        famille_fiscale="Jus EVAM sucré/aromatisé",
        exonere=False, taux_tva=18, taux_centimes_additionnels=5, taux_accise=10,
        sfec_actif=True,
        situation="Règle à retenir pour toutes les recettes de jus décrites "
                  "(eau traitée + sucre + arôme/colorant).",
    ),
    dict(
        code="EV-FISC-YAO-18",
        famille_fiscale="Yaourt",
        exonere=False, taux_tva=18, taux_centimes_additionnels=5, taux_accise=0,
        sfec_actif=True,
        situation="Règle actuelle à retenir pour tous les yaourts.",
    ),
]


class Command(BaseCommand):
    help = "Initialise la matrice fiscale (codes + familles fiscales) avec les valeurs du document de référence."

    def handle(self, *args, **options):
        crees = 0
        for donnees in CODES_FISCAUX:
            donnees = dict(donnees)
            nom_famille = donnees.pop("famille_fiscale")
            famille, _ = FamilleFiscale.objects.get_or_create(nom=nom_famille)
            donnees["famille_fiscale"] = famille

            _, cree = CodeFiscal.objects.get_or_create(
                code=donnees["code"], defaults=donnees,
            )
            if cree:
                crees += 1
                self.stdout.write(self.style.SUCCESS(f"  + {donnees['code']} ({nom_famille})"))
            else:
                self.stdout.write(f"  - {donnees['code']} existe déjà, ignoré")
        self.stdout.write(self.style.SUCCESS(f"\nTerminé : {crees} codes fiscaux créés."))