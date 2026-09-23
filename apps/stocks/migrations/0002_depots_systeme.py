"""
Crée les dépôts « système » utilisés automatiquement par les autres
modules (voir DEPOTS_SYSTEME dans apps/stocks/models.py). Sans eux,
le premier mouvement automatique les créait à la volée, et un dépôt
créé à la main sous un autre nom (ex : « Dépôt matières premières »)
n'était jamais utilisé.
"""

from django.db import migrations

DEPOTS_SYSTEME = {
    "Magasin principal": "Matières premières et emballages",
    "Dépôt produits finis": "Produits finis libérés",
    "Quarantaine": "Zone de quarantaine - retours clients",
}


def creer_depots_systeme(apps, schema_editor):
    Depot = apps.get_model("stocks", "Depot")
    for nom, adresse in DEPOTS_SYSTEME.items():
        depot = Depot.objects.filter(nom__iexact=nom).first()
        if depot is None:
            Depot.objects.create(nom=nom, adresse=adresse, actif=True)
        elif not depot.actif:
            depot.actif = True
            depot.save(update_fields=["actif"])


class Migration(migrations.Migration):

    dependencies = [
        ("stocks", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(creer_depots_systeme, migrations.RunPython.noop),
    ]
