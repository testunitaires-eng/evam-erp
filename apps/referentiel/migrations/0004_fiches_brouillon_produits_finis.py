"""
Règle : tout produit fini a une fiche de composition. Les produits
finis créés AVANT cette règle reçoivent ici leur fiche v1 en brouillon
(créée au nom du premier Administrateur SI / superutilisateur trouvé).
S'il n'existe encore aucun compte, rien n'est fait : les fiches seront
créées au prochain enregistrement de chaque article.
"""

from django.db import migrations


def creer_fiches_manquantes(apps, schema_editor):
    Article = apps.get_model("referentiel", "Article")
    FicheTechnique = apps.get_model("referentiel", "FicheTechnique")
    Utilisateur = apps.get_model("comptes", "Utilisateur")
    auteur = (
        Utilisateur.objects.filter(profil="ADMIN_SI", is_active=True).order_by("pk").first()
        or Utilisateur.objects.filter(is_superuser=True).order_by("pk").first()
    )
    if auteur is None:
        return
    for article in Article.objects.filter(type_article="PRODUIT_FINI", fiches_techniques__isnull=True):
        FicheTechnique.objects.create(article=article, version=1, statut="BROUILLON", cree_par=auteur)


class Migration(migrations.Migration):

    dependencies = [
        ("referentiel", "0003_listes_deroulantes"),
        ("comptes", "0004_delete_matricedroit"),
    ]

    operations = [
        migrations.RunPython(creer_fiches_manquantes, migrations.RunPython.noop),
    ]
