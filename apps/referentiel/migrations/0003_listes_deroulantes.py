"""
Migration écrite à la main (pas par makemigrations) : convertit les
champs texte libre famille/format/parfum/unite_vente en listes
déroulantes (ForeignKey), SANS PERDRE les valeurs déjà saisies.

Stratégie sûre (compatible PostgreSQL, où on ne peut pas transformer
une colonne texte en clé étrangère par un simple ALTER COLUMN) :
    1. Ajouter les nouvelles colonnes FK sous un nom temporaire.
    2. Lire chaque valeur texte existante, créer la ligne de la liste
       déroulante correspondante si elle n'existe pas déjà, et relier
       l'article à cette ligne.
    3. Supprimer les anciennes colonnes texte.
    4. Renommer les colonnes temporaires vers leur nom définitif.

Django l'aurait fait par un simple AlterField texte -> FK, ce qui
échoue sur PostgreSQL (impossible de convertir "Eau" en identifiant
numérique) et aurait de toute façon perdu les données sur SQLite.
"""

import django.db.models.deletion
from django.db import migrations, models


def convertir_champs_texte_en_listes(apps, schema_editor):
    Article = apps.get_model("referentiel", "Article")
    FamilleArticle = apps.get_model("referentiel", "FamilleArticle")
    FormatArticle = apps.get_model("referentiel", "FormatArticle")
    Parfum = apps.get_model("referentiel", "Parfum")
    UniteVenteArticle = apps.get_model("referentiel", "UniteVenteArticle")

    for article in Article.objects.all():
        champs_a_mettre_a_jour = []

        if article.famille_ancien_texte:
            famille, _ = FamilleArticle.objects.get_or_create(nom=article.famille_ancien_texte.strip())
            article.famille_nouveau = famille
            champs_a_mettre_a_jour.append("famille_nouveau")

        if article.format_ancien_texte:
            format_obj, _ = FormatArticle.objects.get_or_create(valeur=article.format_ancien_texte.strip())
            article.format_nouveau = format_obj
            champs_a_mettre_a_jour.append("format_nouveau")

        if article.parfum_ancien_texte:
            parfum, _ = Parfum.objects.get_or_create(nom=article.parfum_ancien_texte.strip())
            article.parfum_nouveau = parfum
            champs_a_mettre_a_jour.append("parfum_nouveau")

        if article.unite_vente_ancien_texte:
            unite, _ = UniteVenteArticle.objects.get_or_create(nom=article.unite_vente_ancien_texte.strip())
            article.unite_vente_nouveau = unite
            champs_a_mettre_a_jour.append("unite_vente_nouveau")

        if champs_a_mettre_a_jour:
            article.save(update_fields=champs_a_mettre_a_jour)


class Migration(migrations.Migration):

    dependencies = [
        ('referentiel', '0002_article_activite_analytique_article_centre_cout_and_more'),
    ]

    operations = [
        # --- 1. Créer les 4 tables de listes déroulantes ---
        migrations.CreateModel(
            name='FamilleArticle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=50, unique=True, verbose_name='Famille')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
            ],
            options={
                'verbose_name': "Famille d'article",
                'verbose_name_plural': "Familles d'article",
                'ordering': ['nom'],
            },
        ),
        migrations.CreateModel(
            name='FormatArticle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valeur', models.CharField(max_length=30, unique=True, verbose_name='Format')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
            ],
            options={
                'verbose_name': "Format d'article",
                'verbose_name_plural': "Formats d'article",
                'ordering': ['valeur'],
            },
        ),
        migrations.CreateModel(
            name='Parfum',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=50, unique=True, verbose_name='Parfum / variante')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
            ],
            options={
                'verbose_name': 'Parfum / variante',
                'verbose_name_plural': 'Parfums / variantes',
                'ordering': ['nom'],
            },
        ),
        migrations.CreateModel(
            name='UniteVenteArticle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=50, unique=True, verbose_name='Unité de vente')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
            ],
            options={
                'verbose_name': 'Unité de vente',
                'verbose_name_plural': 'Unités de vente',
                'ordering': ['nom'],
            },
        ),

        # --- 2. Renommer les anciennes colonnes texte (conservées le temps de la conversion) ---
        migrations.RenameField(model_name='article', old_name='famille', new_name='famille_ancien_texte'),
        migrations.RenameField(model_name='article', old_name='format', new_name='format_ancien_texte'),
        migrations.RenameField(model_name='article', old_name='parfum', new_name='parfum_ancien_texte'),
        migrations.RenameField(model_name='article', old_name='unite_vente', new_name='unite_vente_ancien_texte'),

        # --- 3. Ajouter les nouvelles colonnes FK, sous un nom temporaire ---
        migrations.AddField(
            model_name='article', name='famille_nouveau',
            field=models.ForeignKey(blank=True, help_text='Choisie dans la liste (Eau, Jus, Yaourt...) - plus de saisie libre.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='articles', to='referentiel.famillearticle', verbose_name='Famille'),
        ),
        migrations.AddField(
            model_name='article', name='format_nouveau',
            field=models.ForeignKey(blank=True, help_text='Choisi dans la liste (70 cl, 100 cl, 125 g...).', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='articles', to='referentiel.formatarticle', verbose_name='Format'),
        ),
        migrations.AddField(
            model_name='article', name='parfum_nouveau',
            field=models.ForeignKey(blank=True, help_text='Choisi dans la liste (Nature, Grenadine, Fraise...) - vide si non applicable.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='articles', to='referentiel.parfum', verbose_name='Parfum / variante'),
        ),
        migrations.AddField(
            model_name='article', name='unite_vente_nouveau',
            field=models.ForeignKey(blank=True, help_text="Choisie dans la liste (Pack de 8, Carton de 12...) - l'unité réellement facturée au client.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name='articles', to='referentiel.uniteventearticle', verbose_name='Unité de vente'),
        ),

        # --- 4. Convertir : lit les anciennes colonnes texte, remplit les nouvelles FK ---
        migrations.RunPython(convertir_champs_texte_en_listes, migrations.RunPython.noop),

        # --- 5. Supprimer les anciennes colonnes texte (données déjà reprises à l'étape 4) ---
        migrations.RemoveField(model_name='article', name='famille_ancien_texte'),
        migrations.RemoveField(model_name='article', name='format_ancien_texte'),
        migrations.RemoveField(model_name='article', name='parfum_ancien_texte'),
        migrations.RemoveField(model_name='article', name='unite_vente_ancien_texte'),

        # --- 6. Renommer les nouvelles colonnes FK vers leur nom définitif ---
        migrations.RenameField(model_name='article', old_name='famille_nouveau', new_name='famille'),
        migrations.RenameField(model_name='article', old_name='format_nouveau', new_name='format'),
        migrations.RenameField(model_name='article', old_name='parfum_nouveau', new_name='parfum'),
        migrations.RenameField(model_name='article', old_name='unite_vente_nouveau', new_name='unite_vente'),

        # --- 7. Champs annexes ---
        migrations.AlterField(
            model_name='article', name='designation',
            field=models.CharField(blank=True, help_text="Laisser vide pour la générer automatiquement à partir de la famille, du parfum, du format et de l'unité de vente choisis.", max_length=200, verbose_name='Désignation'),
        ),
        migrations.AlterField(
            model_name='article', name='sous_famille',
            field=models.CharField(blank=True, help_text='Reste en saisie libre : aucune liste fixe connue pour ce niveau à ce jour.', max_length=50, verbose_name='Sous-famille'),
        ),
    ]