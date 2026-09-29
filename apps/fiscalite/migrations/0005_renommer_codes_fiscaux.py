"""
Renomme les codes fiscaux existants au format EV-FISC-{PRODUIT}-{TVA}
(ex : EV-FISC-EAU-EXO -> EV-FISC-EAU-0, EV-FISC-JUS-10 -> EV-FISC-JUS-18).
Les liens (articles, lignes de facture) passent par l'identifiant : ils
ne sont pas affectés. Les mentions des anciens codes dans le champ
« situation » sont mises à jour.
"""

from django.db import migrations

from apps.core.codification import code_fiscal_base


def renommer(apps, schema_editor):
    CodeFiscal = apps.get_model("fiscalite", "CodeFiscal")
    codes = list(CodeFiscal.objects.select_related("famille_fiscale").order_by("pk"))
    # 1) Libère tous les codes (évite les collisions pendant le renommage).
    anciens = {code.pk: code.code for code in codes}
    for code in codes:
        code.code = f"TMP-{code.pk}"
        code.save(update_fields=["code"])
    # 2) Attribue les nouveaux codes.
    pris, correspondance = set(), {}
    for code in codes:
        try:
            base = code_fiscal_base(code.famille_fiscale.nom, code.taux_tva, code.exonere)
        except ValueError:
            base = anciens[code.pk]
        nouveau, indice = base, 2
        while nouveau in pris:
            nouveau, indice = f"{base}-{indice}", indice + 1
        pris.add(nouveau)
        correspondance[anciens[code.pk]] = nouveau
        code.code = nouveau
        code.save(update_fields=["code"])
    # 3) Met à jour les renvois textuels entre codes.
    for code in codes:
        situation = code.situation
        for ancien, nouveau in sorted(correspondance.items(), key=lambda paire: -len(paire[0])):
            situation = situation.replace(ancien, nouveau)
        if situation != code.situation:
            code.situation = situation
            code.save(update_fields=["situation"])


class Migration(migrations.Migration):

    dependencies = [
        ("fiscalite", "0004_codification_tva"),
    ]

    operations = [
        migrations.RunPython(renommer, migrations.RunPython.noop),
    ]
