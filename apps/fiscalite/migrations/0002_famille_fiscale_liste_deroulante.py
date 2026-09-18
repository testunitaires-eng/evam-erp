"""
Migration écrite à la main : convertit CodeFiscal.famille_fiscale d'un
champ texte libre vers une liste déroulante (ForeignKey vers
FamilleFiscale), sans perdre les valeurs déjà saisies. Même stratégie
que apps/referentiel/migrations/0003_listes_deroulantes.py : Django
aurait généré un simple AlterField texte -> FK, qui échoue sur
PostgreSQL et perd les données sur SQLite.

famille_fiscale est un champ OBLIGATOIRE (pas de blank=True) sur
CodeFiscal : si jamais une ligne existante avait ce champ vide (ne
devrait normalement pas arriver), elle est rattachée par défaut à la
famille "Non classé" plutôt que de bloquer la migration.
"""

import django.db.models.deletion
from django.db import migrations, models


def convertir_famille_fiscale(apps, schema_editor):
    CodeFiscal = apps.get_model("fiscalite", "CodeFiscal")
    FamilleFiscale = apps.get_model("fiscalite", "FamilleFiscale")

    for code_fiscal in CodeFiscal.objects.all():
        nom = (code_fiscal.famille_fiscale_ancien_texte or "").strip() or "Non classé"
        famille, _ = FamilleFiscale.objects.get_or_create(nom=nom)
        code_fiscal.famille_fiscale_nouveau = famille
        code_fiscal.save(update_fields=["famille_fiscale_nouveau"])


class Migration(migrations.Migration):

    dependencies = [
        ('fiscalite', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='FamilleFiscale',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=150, unique=True, verbose_name='Famille fiscale')),
                ('actif', models.BooleanField(default=True, verbose_name='Actif')),
            ],
            options={
                'verbose_name': 'Famille fiscale',
                'verbose_name_plural': 'Familles fiscales',
                'ordering': ['nom'],
            },
        ),

        migrations.RenameField(model_name='codefiscal', old_name='famille_fiscale', new_name='famille_fiscale_ancien_texte'),

        migrations.AddField(
            model_name='codefiscal', name='famille_fiscale_nouveau',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='codes_fiscaux', to='fiscalite.famillefiscale', verbose_name='Famille fiscale'),
        ),

        migrations.RunPython(convertir_famille_fiscale, migrations.RunPython.noop),

        migrations.RemoveField(model_name='codefiscal', name='famille_fiscale_ancien_texte'),

        migrations.RenameField(model_name='codefiscal', old_name='famille_fiscale_nouveau', new_name='famille_fiscale'),

        # Toutes les lignes ont désormais une famille fiscale : on peut
        # imposer la contrainte NOT NULL, comme sur le modèle final.
        migrations.AlterField(
            model_name='codefiscal', name='famille_fiscale',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='codes_fiscaux', to='fiscalite.famillefiscale', verbose_name='Famille fiscale', help_text="Choisie dans la liste - description métier de la nature fiscale, pas du produit commercial."),
        ),
    ]