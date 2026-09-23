"""
Crée une caisse par défaut si aucune n'existe : sans caisse, le
Caissier ne peut ouvrir aucune session (le frontend n'a pas encore
d'écran de création de caisse). D'autres caisses peuvent être ajoutées
par l'Administrateur SI (API /api/caisse/caisses/ ou admin Django).
"""

from django.db import migrations


def creer_caisse_par_defaut(apps, schema_editor):
    Caisse = apps.get_model("caisse", "Caisse")
    if not Caisse.objects.exists():
        Caisse.objects.create(nom="Caisse principale", emplacement="Siège", actif=True)


class Migration(migrations.Migration):

    dependencies = [
        ("caisse", "0003_decaissement"),
    ]

    operations = [
        migrations.RunPython(creer_caisse_par_defaut, migrations.RunPython.noop),
    ]
