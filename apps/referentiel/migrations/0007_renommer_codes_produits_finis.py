"""
Renomme les produits finis existants au nouveau format
FAMILLE + PARFUM + FORMAT + UNITÉ DE VENTE (ex : EAU70P8, JUSGRE70P8).
Un produit fini auquel il manque une information (famille, format,
unité de vente) ou dont le code serait en doublon garde son ancien code :
il sera recodé dès qu'on complètera sa fiche (tant qu'il n'est pas utilisé).
Les liens passent par l'identifiant : commandes, stocks, OF... ne sont
pas affectés.
"""

from django.db import migrations

from apps.core.codification import code_produit_fini


def renommer(apps, schema_editor):
    Article = apps.get_model("referentiel", "Article")
    produits = Article.objects.filter(type_article="PRODUIT_FINI").select_related(
        "famille", "parfum", "format", "unite_vente",
    ).order_by("pk")
    for article in produits:
        if not (article.famille_id and article.format_id and article.unite_vente_id):
            continue
        try:
            code = code_produit_fini(
                famille=article.famille.nom, format_valeur=article.format.valeur,
                unite_vente=article.unite_vente.nom, parfum=article.parfum.nom if article.parfum_id else None,
            )
        except ValueError:
            continue
        if code != article.code and not Article.objects.filter(code=code).exists():
            article.code = code
            article.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("referentiel", "0006_codification_produits_finis"),
    ]

    operations = [
        migrations.RunPython(renommer, migrations.RunPython.noop),
    ]
