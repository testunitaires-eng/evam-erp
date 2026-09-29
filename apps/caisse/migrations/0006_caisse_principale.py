"""
- Marque la caisse principale (créée par 0004 sous le nom « Caisse
  principale ») comme caisse de consolidation ; la crée si elle
  n'existe pas.
- Traçabilité : renseigne « encaissé par » des encaissements déjà
  enregistrés avec le caissier de leur session.
"""

from django.db import migrations


def marquer_caisse_principale(apps, schema_editor):
    Caisse = apps.get_model("caisse", "Caisse")
    Encaissement = apps.get_model("caisse", "Encaissement")

    principale = Caisse.objects.filter(nom__iexact="Caisse principale").first()
    if principale is None:
        principale = Caisse.objects.create(nom="Caisse principale", emplacement="Siège", actif=True)
    principale.est_principale = True
    principale.actif = True
    principale.caissier = None
    principale.save()

    for encaissement in Encaissement.objects.filter(encaisse_par__isnull=True).select_related("session_caisse"):
        encaissement.encaisse_par_id = encaissement.session_caisse.caissier_id
        encaissement.save(update_fields=["encaisse_par"])


class Migration(migrations.Migration):

    dependencies = [
        ("caisse", "0005_caisses_affectees"),
    ]

    operations = [
        migrations.RunPython(marquer_caisse_principale, migrations.RunPython.noop),
    ]
