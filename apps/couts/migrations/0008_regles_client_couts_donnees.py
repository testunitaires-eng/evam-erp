# Mise à jour des natures de coût, séparée de 0007 : PostgreSQL refuse de créer
# l'index de naturecout.activite dans la transaction qui vient de modifier ces lignes
# (« pending trigger events »).

from django.db import migrations

QP = "QUANTITE_PRODUITE"
BRUTE = "VOLUME_EAU_BRUTE_M3"
FORAGE = "Forage commun aux 3 activités : volume d'eau brute captée (compteurs), puis aux OF selon la quantité produite."
TRAITEMENT = "Local de traitement de l'eau : affectation directe à l'Eau (document « Infrastructures et coût de production »)."
PRODUCTION = "Répartie selon la production (L pour l'Eau et le Jus, kg pour le Yaourt) ; directe si l'activité est connue."

# libellé : (inducteur d'origine attendu, nouveaux champs). Une nature déjà
# modifiée par la DAF (inducteur différent) n'est pas touchée.
MISES_A_JOUR = {
    "Électricité des pompes de forage": ("VOLUME_EAU_M3", {"inducteur": BRUTE, "justification": FORAGE}),
    "Maintenance des pompes de forage": ("VOLUME_EAU_M3", {"inducteur": BRUTE, "justification": FORAGE}),
    "Pièces de rechange / lubrifiants captage": ("VOLUME_EAU_M3", {"inducteur": BRUTE, "justification": FORAGE}),
    "Main-d'œuvre captage": ("VOLUME_EAU_M3", {"inducteur": BRUTE, "justification": FORAGE}),
    "Analyses eau brute": ("ANALYSES_PONDEREES", {"inducteur": BRUTE, "justification": FORAGE}),
    "Électricité traitement de l'eau": ("VOLUME_EAU_M3", {"inducteur": QP, "traitement": "DIRECT", "eau": True, "justification": TRAITEMENT}),
    "Filtres / membranes": ("VOLUME_EAU_M3", {"inducteur": QP, "traitement": "DIRECT", "eau": True, "justification": TRAITEMENT}),
    "Produits chimiques de traitement": ("VOLUME_EAU_M3", {"inducteur": QP, "traitement": "DIRECT", "eau": True, "justification": TRAITEMENT}),
    "Maintenance traitement de l'eau": ("VOLUME_EAU_M3", {"inducteur": QP, "traitement": "DIRECT", "eau": True, "justification": TRAITEMENT}),
    "Main-d'œuvre traitement de l'eau": ("VOLUME_EAU_M3", {"inducteur": QP, "traitement": "DIRECT", "eau": True, "justification": TRAITEMENT}),
    "Électricité pompes cuves process": ("VOLUME_EAU_M3", {"inducteur": QP}),
    "Nettoyage / désinfection cuves": ("VOLUME_EAU_M3", {"inducteur": QP}),
    "Maintenance cuves": ("VOLUME_EAU_M3", {"inducteur": QP}),
    "Électricité préparation": ("HEURES_MACHINE", {"inducteur": QP, "justification": PRODUCTION}),
    "Main-d'œuvre préparation": ("HEURES_MO", {"inducteur": QP, "justification": PRODUCTION}),
    "Nettoyage préparation": ("HEURES_MACHINE", {"inducteur": QP, "justification": PRODUCTION}),
    "Analyses qualité préparation": ("ANALYSES_PONDEREES", {"inducteur": QP, "justification": "Laboratoire : selon l'activité bénéficiaire (directe si connue), sinon la production."}),
    "Électricité soufflage": ("HEURES_MACHINE", {"inducteur": QP, "justification": "Selon l'activité utilisatrice : directe si connue, sinon la production."}),
    "Main-d'œuvre soufflage": ("HEURES_MO", {"inducteur": QP, "justification": PRODUCTION}),
    "Électricité remplissage": ("HEURES_MACHINE", {"inducteur": QP, "justification": PRODUCTION}),
    "Main-d'œuvre remplissage": ("HEURES_MO", {"inducteur": QP, "justification": PRODUCTION}),
    "Électricité bouchage": ("HEURES_MACHINE", {"inducteur": QP, "justification": PRODUCTION}),
    "Électricité étiquetage": ("HEURES_MACHINE", {"inducteur": QP, "justification": PRODUCTION}),
    "Main-d'œuvre étiquetage": ("HEURES_MO", {"inducteur": QP, "justification": PRODUCTION}),
    "Électricité plastification": ("HEURES_MACHINE", {"inducteur": QP, "justification": PRODUCTION}),
    "Main-d'œuvre plastification": ("HEURES_MO", {"inducteur": QP, "justification": PRODUCTION}),
    "Palettisation (personnel, film palette)": ("PALETTES", {"inducteur": QP, "justification": PRODUCTION}),
    "Réactifs / consommables laboratoire": ("ANALYSES_PONDEREES", {"inducteur": QP, "justification": "Laboratoire : selon l'activité bénéficiaire (directe si connue), sinon la production."}),
    "Personnel qualité": ("ANALYSES_PONDEREES", {"inducteur": QP, "justification": "Laboratoire : selon l'activité bénéficiaire (directe si connue), sinon la production."}),
    "Électricité utilités du site (air comprimé, froid, chaufferie)": ("LITRES_PRODUITS", {"inducteur": QP}),
    # Maintenance : « affectation directe ou heures d'utilisation » (inducteur conservé).
    "Maintenance mélangeurs": ("HEURES_MACHINE", {}),
    "Maintenance souffleuse": ("HEURES_MACHINE", {}),
    "Maintenance remplisseuse": ("HEURES_MACHINE", {}),
    "Maintenance boucheuse": ("HEURES_MACHINE", {}),
    "Maintenance fardeleuse": ("HEURES_MACHINE", {}),
    # Infrastructures de production : dans le coût de production (document client).
    "Électricité commune des infrastructures (bâtiments, éclairage, sécurité)": ("SURFACE_M2", {
        "justification": "Infrastructure de production : surface occupée, puis aux OF selon la quantité produite."}),
    "Autres charges communes des infrastructures (gardiennage, entretien bâtiments)": ("SURFACE_M2", {
        "justification": "Infrastructure de production : surface occupée, puis aux OF selon la quantité produite."}),
}

# libellé, étape, catégorie, catégorie économique, inducteur, justification
NOUVELLES = [
    ("Sécurité des zones de production", "FRAIS_SITE", "PRODUCTION", "AUTRE", "SURFACE_M2",
     "Surface ou autre clé pertinente, puis aux OF selon la quantité produite."),
    ("Nettoyage des zones de production", "FRAIS_SITE", "PRODUCTION", "PRODUITS_TRAITEMENT", "SURFACE_M2",
     "Surface occupée, puis aux OF selon la quantité produite."),
    ("Stockage des matières premières et emballages", "FRAIS_SITE", "PRODUCTION", "LOCATION", "SURFACE_M2",
     "Directe si le magasin est dédié à une activité ; sinon surface, puis aux OF selon la quantité produite."),
    ("Électricité chambre froide de production", "UTILITES", "PRODUCTION", "ENERGIE", "VOLUME_OCCUPE_M3",
     "Selon utilisation : volume occupé (m³) ou emplacements de palettes (clé au choix), puis aux OF selon la quantité produite."),
    ("Points de vente et caisses (personnel, loyer, électricité)", None, "COMMERCIAL", "AUTRE", "CHIFFRE_AFFAIRES",
     "Commercialisation : hors coût de production, dans le coût de revient ; répartie au chiffre d'affaires."),
]


def appliquer(apps, schema_editor):
    NatureCout = apps.get_model("couts", "NatureCout")
    EtapeStandard = apps.get_model("industriel", "EtapeStandard")
    Activite = apps.get_model("industriel", "Activite")
    eau = Activite.objects.filter(code="EAU").first()
    for libelle, (origine, champs) in MISES_A_JOUR.items():
        nature = NatureCout.objects.filter(libelle=libelle).first()
        if nature is None or nature.inducteur != origine:
            continue
        champs = dict(champs)
        if champs.pop("eau", False):
            nature.activite = eau
        for champ, valeur in champs.items():
            setattr(nature, champ, valeur)
        nature.inducteur_of = QP
        nature.save()
    rang = max((int(c[4:]) for c in NatureCout.objects.values_list("code", flat=True) if c[4:].isdigit()), default=0)
    for libelle, etape, categorie, economique, inducteur, justification in NOUVELLES:
        if NatureCout.objects.filter(libelle=libelle).exists():
            continue
        rang += 1
        NatureCout.objects.create(
            code=f"NAT-{rang:03d}", libelle=libelle, etape=EtapeStandard.objects.filter(code=etape).first() if etape else None,
            categorie=categorie, categorie_economique=economique, traitement="INDIRECT", inducteur=inducteur,
            inducteur_of=QP if categorie == "PRODUCTION" else "", justification=justification,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('couts', '0007_regles_client_couts'),
    ]

    operations = [
        migrations.RunPython(appliquer, migrations.RunPython.noop),
    ]
