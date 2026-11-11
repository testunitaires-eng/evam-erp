"""
Étapes du traitement de l'eau du classeur EVAM (onglet Paramétrage :
« Captage -> Préfiltration -> Ultrafiltration -> Cuves -> UV ; Contrôle
qualité »), ajoutées comme sous-étapes du Traitement de l'eau.

Les étapes déjà présentes (Décantation, Filtration, Cuve tampon, UV)
sont conservées : le schéma du procédé (PDF) et le classeur ne décrivent
pas encore la même chaîne, la liste définitive est à valider avec le
technicien. Toutes restent modifiables dans le paramétrage.

Idempotente : ne crée que ce qui n'existe pas encore.
"""

from django.db import migrations

# code, libellé, ordre, description
ETAPES = [
    ("PREFILTRATION", "Préfiltration", 21, "Filtre à sable, charbon actif, adoucisseur (résine et sel de régénération)."),
    ("ULTRAFILTRATION", "Ultrafiltration", 22, "Module d'ultrafiltration et membranes (DP1 à DP3)."),
    ("CUVES_EAU", "Cuves d'eau brute et d'eau traitée", 23, "Stockage de l'eau avant et après traitement."),
    ("CONTROLE_QUALITE_EAU", "Contrôle qualité de l'eau", 25, "Analyses par laboratoire externe et contrôles internes (kits)."),
]


def installer(apps, schema_editor):
    EtapeStandard = apps.get_model("industriel", "EtapeStandard")
    traitement = EtapeStandard.objects.filter(code="TRAITEMENT").first()
    for code, libelle, ordre, description in ETAPES:
        EtapeStandard.objects.get_or_create(code=code, defaults={
            "libelle": libelle, "phase": "AMONT", "ordre_reference": ordre,
            "sous_etape_de": traitement, "description": description,
        })


class Migration(migrations.Migration):

    dependencies = [
        ("eau", "0001_initial"),
        ("industriel", "0005_regles_client_couts"),
    ]

    operations = [migrations.RunPython(installer, migrations.RunPython.noop)]
