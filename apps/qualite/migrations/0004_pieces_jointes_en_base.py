"""
Pièces jointes qualité conservées en base (et non plus sur le disque du
conteneur, effacé à chaque redéploiement Railway). Les fichiers déjà
déposés sont repris s'ils sont encore lisibles.
"""

import mimetypes
import os

from django.db import migrations, models


def reprendre_fichiers(apps, schema_editor):
    PieceJointeQualite = apps.get_model("qualite", "PieceJointeQualite")
    for piece in PieceJointeQualite.objects.exclude(fichier=""):
        try:
            with piece.fichier.open("rb") as source:
                contenu = source.read()
        except (OSError, ValueError):
            contenu = b""   # fichier déjà perdu (disque du conteneur) : la fiche est conservée
        nom = os.path.basename(piece.fichier.name)
        piece.contenu = contenu
        piece.taille = len(contenu)
        piece.nom_fichier = nom[:200]
        piece.type_contenu = mimetypes.guess_type(nom)[0] or "application/octet-stream"
        piece.save(update_fields=["contenu", "taille", "nom_fichier", "type_contenu"])


class Migration(migrations.Migration):

    dependencies = [
        ("qualite", "0003_nonconformite_lot_matiere_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="piecejointequalite", name="nom_fichier",
            field=models.CharField(default="", max_length=200, verbose_name="Nom du fichier"), preserve_default=False,
        ),
        migrations.AddField(
            model_name="piecejointequalite", name="type_contenu",
            field=models.CharField(default="", max_length=60, verbose_name="Type"), preserve_default=False,
        ),
        migrations.AddField(
            model_name="piecejointequalite", name="taille",
            field=models.PositiveIntegerField(default=0, verbose_name="Taille (octets)"),
        ),
        migrations.AddField(
            model_name="piecejointequalite", name="contenu",
            field=models.BinaryField(default=b"", editable=False, verbose_name="Contenu"), preserve_default=False,
        ),
        migrations.RunPython(reprendre_fichiers, migrations.RunPython.noop),
        migrations.RemoveField(model_name="piecejointequalite", name="fichier"),
    ]
