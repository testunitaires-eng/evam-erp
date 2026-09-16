import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fiscalite', '0001_initial'),
        ('referentiel', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='activite_analytique',
            field=models.CharField(blank=True, max_length=100, verbose_name='Activité analytique'),
        ),
        migrations.AddField(
            model_name='article',
            name='centre_cout',
            field=models.CharField(blank=True, max_length=100, verbose_name='Centre de coût'),
        ),
        migrations.AddField(
            model_name='article',
            name='code_fiscal',
            field=models.ForeignKey(blank=True, help_text="Détermine automatiquement la TVA, l'accise et les centimes additionnels appliqués à la facturation.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name='articles', to='fiscalite.codefiscal', verbose_name='Code fiscal'),
        ),
        migrations.AddField(
            model_name='article',
            name='compte_vente',
            field=models.CharField(blank=True, help_text="Ex : 701200 - utilisé pour l'export vers Sage 100.", max_length=30, verbose_name='Compte de vente (comptabilité)'),
        ),
        migrations.AddField(
            model_name='article',
            name='duree_conservation_jours',
            field=models.PositiveIntegerField(blank=True, help_text="Sert à calculer la DLC/DDM d'un lot à sa date de fabrication. Laisser vide si non périssable.", null=True, verbose_name='Durée de conservation (jours)'),
        ),
        migrations.AddField(
            model_name='article',
            name='emplacement_stockage',
            field=models.CharField(blank=True, max_length=100, verbose_name='Emplacement de stockage par défaut'),
        ),
        migrations.AddField(
            model_name='article',
            name='format',
            field=models.CharField(blank=True, help_text='Ex : 70 cl, 100 cl, 125 g', max_length=30, verbose_name='Format'),
        ),
        migrations.AddField(
            model_name='article',
            name='marque',
            field=models.CharField(blank=True, default='EVAM', max_length=50, verbose_name='Marque'),
        ),
        migrations.AddField(
            model_name='article',
            name='parfum',
            field=models.CharField(blank=True, help_text='Ex : Grenadine, Nature, Fraise (vide si non applicable)', max_length=50, verbose_name='Parfum / variante'),
        ),
        migrations.AddField(
            model_name='article',
            name='sous_famille',
            field=models.CharField(blank=True, max_length=50, verbose_name='Sous-famille'),
        ),
        migrations.AddField(
            model_name='article',
            name='stock_alerte',
            field=models.DecimalField(decimal_places=3, default=0, help_text="Seuil d'alerte précoce, avant la rupture (stock_minimum).", max_digits=14, verbose_name="Stock d'alerte"),
        ),
        migrations.AddField(
            model_name='article',
            name='stock_minimum',
            field=models.DecimalField(decimal_places=3, default=0, help_text='Seuil déclenchant une alerte de rupture.', max_digits=14, verbose_name='Stock minimum'),
        ),
        migrations.AddField(
            model_name='article',
            name='suivi_par_lot',
            field=models.BooleanField(default=True, help_text='Un produit fabriqué doit presque toujours être suivi par lot (traçabilité).', verbose_name='Suivi par lot'),
        ),
        migrations.AddField(
            model_name='article',
            name='unite_vente',
            field=models.CharField(blank=True, help_text="Ex : Pack de 8, Carton de 12 - l'unité réellement facturée au client.", max_length=50, verbose_name='Unité de vente'),
        ),
        migrations.AlterField(
            model_name='article',
            name='unite_mesure',
            field=models.CharField(choices=[('KG', 'Kilogramme'), ('L', 'Litre'), ('UNITE', 'Unité'), ('CARTON', 'Carton'), ('PALETTE', 'Palette'), ('M', 'Mètre')], help_text='Unité de gestion interne (ex : Unité pour une bouteille).', max_length=10, verbose_name='Unité de base'),
        ),
        migrations.CreateModel(
            name='ControleQualiteRequis',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_controle', models.CharField(help_text='Ex : pH, Microbiologie, Aspect/emballage, Brix (taux de sucre)', max_length=100, verbose_name='Type de contrôle')),
                ('norme_ou_seuil', models.CharField(help_text="Ex : 'Conforme au standard EVAM', 'pH entre 3,5 et 4,2'", max_length=200, verbose_name='Norme ou seuil attendu')),
                ('moment', models.CharField(choices=[('APRES_TRAITEMENT', 'Après traitement'), ('AVANT_LIBERATION', 'Avant libération du lot'), ('FIN_DE_LIGNE', 'Fin de ligne'), ('RECEPTION', 'À réception'), ('AUTRE', 'Autre')], max_length=20, verbose_name='Moment du contrôle')),
                ('obligatoire', models.BooleanField(default=True, help_text="Si coché, le lot ne peut pas être libéré (voir apps.qualite) tant que ce contrôle n'a pas un résultat conforme.", verbose_name='Obligatoire avant libération')),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='controles_qualite_requis', to='referentiel.article', verbose_name='Article')),
            ],
            options={
                'verbose_name': 'Contrôle qualité requis',
                'verbose_name_plural': 'Contrôles qualité requis (paramétrage)',
                'ordering': ['article', 'moment'],
            },
        ),
    ]