"""
Paramétrage de référence repris des documents EVAM (Guide du paramétrage
général, Circuit complet de production, Clés d'imputation des coûts,
Contrôle qualité Eau / Jus / Yaourt) :

- activités EAU, JUS, YAOURT et usines US-EAU, US-JY ;
- étapes standard du circuit de référence et circuits Eau / Jus / Yaourt ;
- rattachement des familles et produits finis existants à leur activité,
  contenance et unités par pack déduites du format / de l'unité de vente ;
- types des lieux de stockage existants ;
- éléments de coût avec leur étape, traitement et inducteur ;
- paramètres qualité (noms uniquement : aucune valeur cible, aucun seuil,
  aucune fréquence n'est inventé - ils viendront des fiches validées).

Idempotente : ne crée que ce qui n'existe pas encore.
"""

from django.db import migrations

ACTIVITES = [("EAU", "Eau"), ("JUS", "Jus"), ("YAOURT", "Yaourt")]
USINES = [("US-EAU", "Usine Eau", ["EAU"]), ("US-JY", "Usine Jus & Yaourt", ["JUS", "YAOURT"])]

# code, libellé, phase, ordre, sous-étape de, description
ETAPES = [
    ("CAPTAGE", "Captage / forage", "AMONT", 10, None, "Prélèvement de l'eau. Le forage est commun aux activités Eau, Jus et Yaourt."),
    ("TRAITEMENT", "Traitement de l'eau", "AMONT", 20, None, "Obtention de l'eau traitée utilisable dans les procédés."),
    ("DECANTATION", "Décantation", "AMONT", 21, "TRAITEMENT", ""),
    ("FILTRATION", "Filtration / traitement", "AMONT", 22, "TRAITEMENT", ""),
    ("CUVE_TAMPON", "Cuve tampon", "AMONT", 23, "TRAITEMENT", ""),
    ("UV", "Traitement UV", "AMONT", 24, "TRAITEMENT", ""),
    ("STOCKAGE_PROCESS", "Stockage process (cuve dédiée)", "AMONT", 30, None, "Eau traitée stockée dans des cuves dédiées aux activités."),
    ("PREPARATION", "Préparation du produit", "PREPARATION", 40, None, "Jus : recette (dosage, mélange) ; Yaourt : formulation. Pas pour l'Eau."),
    ("TRAITEMENT_THERMIQUE", "Traitement thermique (pasteurisation)", "PREPARATION", 45, None, "Chauffage, maintien, refroidissement."),
    ("SOUFFLAGE", "Soufflage", "CONDITIONNEMENT", 50, None, "Préformes PET -> bouteilles, si la bouteille est soufflée sur site."),
    ("REMPLISSAGE", "Remplissage", "CONDITIONNEMENT", 60, None, "Introduction du produit dans les bouteilles ou pots."),
    ("BOUCHAGE", "Bouchage / capsulage / operculage", "CONDITIONNEMENT", 70, None, "Fermeture du contenant."),
    ("ETIQUETAGE", "Étiquetage", "CONDITIONNEMENT", 80, None, "Après remplissage et bouchage, avant la plastification."),
    ("CONDITIONNEMENT", "Conditionnement secondaire / plastification", "CONDITIONNEMENT", 90, None, "Mise en pack et film plastique."),
    ("PALETTISATION", "Palettisation", "CONDITIONNEMENT", 100, None, "Regroupement des packs sur palettes."),
    ("STOCKAGE_PF", "Stockage produit fini", "APRES_PRODUCTION", 110, None, "Entrée du produit conforme en stock (hors coût de production)."),
    ("DISTRIBUTION", "Expédition / distribution", "APRES_PRODUCTION", 120, None, "Transferts, livraisons (hors coût de production)."),
]

# (code étape, obligatoire)
CIRCUITS = {
    "EAU": [("CAPTAGE", True), ("TRAITEMENT", True), ("STOCKAGE_PROCESS", True), ("SOUFFLAGE", False),
            ("REMPLISSAGE", True), ("BOUCHAGE", True), ("ETIQUETAGE", True), ("CONDITIONNEMENT", False),
            ("PALETTISATION", True), ("STOCKAGE_PF", True)],
    "JUS": [("CAPTAGE", True), ("TRAITEMENT", True), ("STOCKAGE_PROCESS", True), ("PREPARATION", True),
            ("TRAITEMENT_THERMIQUE", False), ("SOUFFLAGE", False), ("REMPLISSAGE", True), ("BOUCHAGE", True),
            ("ETIQUETAGE", True), ("CONDITIONNEMENT", False), ("PALETTISATION", True), ("STOCKAGE_PF", True)],
    "YAOURT": [("CAPTAGE", True), ("TRAITEMENT", True), ("STOCKAGE_PROCESS", True), ("PREPARATION", True),
               ("REMPLISSAGE", True), ("BOUCHAGE", True), ("ETIQUETAGE", True), ("CONDITIONNEMENT", True),
               ("PALETTISATION", True), ("STOCKAGE_PF", True)],
}

# libellé, étape, catégorie, catégorie économique, traitement, inducteur, justification
P, I, D = "PRODUCTION", "INDIRECT", "DIRECT"
NATURES = [
    ("Électricité des pompes de forage", "CAPTAGE", P, "ENERGIE", I, "VOLUME_EAU_M3", "Forage commun : volume d'eau affecté (ne pas présenter la quote-part comme des kWh mesurés)."),
    ("Maintenance des pompes de forage", "CAPTAGE", P, "MAINTENANCE", I, "VOLUME_EAU_M3", "Pompe commune : volume d'eau affecté ou heures d'utilisation."),
    ("Pièces de rechange / lubrifiants captage", "CAPTAGE", P, "PIECES", I, "VOLUME_EAU_M3", "Direct si la pièce est dédiée à une activité."),
    ("Main-d'œuvre captage", "CAPTAGE", P, "MAIN_OEUVRE", I, "VOLUME_EAU_M3", "Feuille de temps recommandée."),
    ("Analyses eau brute", "CAPTAGE", P, "ANALYSES", I, "ANALYSES_PONDEREES", "Une analyse coûteuse ne pèse pas comme une analyse simple."),
    ("Électricité traitement de l'eau", "TRAITEMENT", P, "ENERGIE", I, "VOLUME_EAU_M3", "Compteur dédié = direct ; sinon volume traité."),
    ("Filtres / membranes", "TRAITEMENT", P, "PRODUITS_TRAITEMENT", I, "VOLUME_EAU_M3", "Direct si affectable à une activité ; sinon volume traité."),
    ("Produits chimiques de traitement", "TRAITEMENT", P, "PRODUITS_TRAITEMENT", I, "VOLUME_EAU_M3", "Direct si la consommation est connue ; sinon volume traité."),
    ("Maintenance traitement de l'eau", "TRAITEMENT", P, "MAINTENANCE", I, "VOLUME_EAU_M3", "Heures d'utilisation ou volume traité selon l'installation."),
    ("Main-d'œuvre traitement de l'eau", "TRAITEMENT", P, "MAIN_OEUVRE", I, "VOLUME_EAU_M3", "Heures réellement affectées."),
    ("Électricité pompes cuves process", "STOCKAGE_PROCESS", P, "ENERGIE", D, "VOLUME_EAU_M3", "Cuves dédiées : direct à l'activité."),
    ("Nettoyage / désinfection cuves", "STOCKAGE_PROCESS", P, "PRODUITS_TRAITEMENT", D, "VOLUME_EAU_M3", "Cuve dédiée : direct à l'activité."),
    ("Maintenance cuves", "STOCKAGE_PROCESS", P, "MAINTENANCE", D, "VOLUME_EAU_M3", "Cuve dédiée : coût réel de l'activité."),
    ("Électricité préparation", "PREPARATION", P, "ENERGIE", I, "HEURES_MACHINE", "Compteur dédié = direct ; sinon heures machine."),
    ("Main-d'œuvre préparation", "PREPARATION", P, "MAIN_OEUVRE", I, "HEURES_MO", "Direct si temps tracé."),
    ("Nettoyage préparation", "PREPARATION", P, "PRODUITS_TRAITEMENT", I, "HEURES_MACHINE", "Temps ou quantité consommée."),
    ("Maintenance mélangeurs", "PREPARATION", P, "MAINTENANCE", I, "HEURES_MACHINE", "Direct si équipement dédié."),
    ("Analyses qualité préparation", "PREPARATION", P, "ANALYSES", I, "ANALYSES_PONDEREES", "Nombre ou coût pondéré des analyses."),
    ("Électricité soufflage", "SOUFFLAGE", P, "ENERGIE", I, "HEURES_MACHINE", "Compteur dédié = direct ; sinon heures machine."),
    ("Main-d'œuvre soufflage", "SOUFFLAGE", P, "MAIN_OEUVRE", I, "HEURES_MO", "Direct si temps tracé."),
    ("Maintenance souffleuse", "SOUFFLAGE", P, "MAINTENANCE", I, "HEURES_MACHINE", "Heures d'utilisation."),
    ("Électricité remplissage", "REMPLISSAGE", P, "ENERGIE", I, "HEURES_MACHINE", "kWh mesurés ou heures machine."),
    ("Main-d'œuvre remplissage", "REMPLISSAGE", P, "MAIN_OEUVRE", I, "HEURES_MO", "Heures réellement affectées."),
    ("Maintenance remplisseuse", "REMPLISSAGE", P, "MAINTENANCE", I, "HEURES_MACHINE", "Heures d'utilisation ou coût réel."),
    ("Électricité bouchage", "BOUCHAGE", P, "ENERGIE", I, "HEURES_MACHINE", "Compteur ou heures machine."),
    ("Maintenance boucheuse", "BOUCHAGE", P, "MAINTENANCE", I, "HEURES_MACHINE", "Heures d'utilisation."),
    ("Électricité étiquetage", "ETIQUETAGE", P, "ENERGIE", I, "HEURES_MACHINE", "kWh / heures machine."),
    ("Main-d'œuvre étiquetage", "ETIQUETAGE", P, "MAIN_OEUVRE", I, "HEURES_MO", "Heures réellement affectées."),
    ("Électricité plastification", "CONDITIONNEMENT", P, "ENERGIE", I, "HEURES_MACHINE", "Compteur ou heures machine."),
    ("Main-d'œuvre plastification", "CONDITIONNEMENT", P, "MAIN_OEUVRE", I, "HEURES_MO", "Heures réellement affectées."),
    ("Maintenance fardeleuse", "CONDITIONNEMENT", P, "MAINTENANCE", I, "HEURES_MACHINE", "Heures machine / coût réel."),
    ("Palettisation (personnel, film palette)", "PALETTISATION", P, "AUTRE", I, "PALETTES", "Nombre de palettes."),
    ("Réactifs / consommables laboratoire", None, P, "ANALYSES", I, "ANALYSES_PONDEREES", "Coût réel ou analyses pondérées."),
    ("Personnel qualité", None, P, "MAIN_OEUVRE", I, "ANALYSES_PONDEREES", "Direct si temps tracé ; sinon analyses pondérées."),
    ("Analyses externes", None, P, "ANALYSES", D, "ANALYSES_PONDEREES", "Direct au lot / à l'OF : coût réel de l'analyse."),
    ("Bâtiment / location stockage produits finis", "STOCKAGE_PF", "STOCKAGE", "LOCATION", I, "PALETTES_JOURS", "Palettes-jours ou surface occupée."),
    ("Électricité dépôt produits finis", "STOCKAGE_PF", "STOCKAGE", "ENERGIE", I, "PALETTES_JOURS", "Coût de stockage."),
    ("Personnel magasin produits finis", "STOCKAGE_PF", "STOCKAGE", "MAIN_OEUVRE", I, "PALETTES_JOURS", "Heures ou palettes manipulées."),
    ("Carburant", "DISTRIBUTION", "DISTRIBUTION", "CARBURANT", D, "KM", "Direct à la tournée : km / consommation réelle."),
    ("Chauffeurs", "DISTRIBUTION", "DISTRIBUTION", "MAIN_OEUVRE", D, "KM", "Direct à la tournée si temps tracé."),
    ("Péages / parking", "DISTRIBUTION", "DISTRIBUTION", "CARBURANT", D, "KM", "Coût réel de la tournée."),
    ("Sous-traitance transport", "DISTRIBUTION", "DISTRIBUTION", "SOUS_TRAITANCE", D, "QUANTITE_LIVREE", "Coût facture de la tournée."),
    ("Frais généraux (administration, direction)", None, "HORS_COUT", "AUTRE", I, "AUCUN", "Pas de lien défendable avec le produit : non incorporés."),
]

# libellé, famille, type de résultat, unité
PARAMETRES = [
    ("pH", "PHYSICO_CHIMIQUE", "NUMERIQUE", "pH"),
    ("Brix / taux de sucre", "PHYSICO_CHIMIQUE", "NUMERIQUE", "°Brix"),
    ("Température", "PROCESS", "NUMERIQUE", "°C"),
    ("Débit", "PROCESS", "NUMERIQUE", "m³/h"),
    ("Pression", "PROCESS", "NUMERIQUE", "bar"),
    ("Niveau", "PROCESS", "NUMERIQUE", "%"),
    ("Volume rempli", "CONDITIONNEMENT", "NUMERIQUE", "mL"),
    ("Poids bouteille", "CONDITIONNEMENT", "NUMERIQUE", "g"),
    ("Serrage bouchon", "CONDITIONNEMENT", "NUMERIQUE", "N·m"),
    ("Présence / fermeture bouchon", "CONDITIONNEMENT", "QUALITATIF", ""),
    ("Étiquette (présence, référence, date, lot, position)", "CONDITIONNEMENT", "QUALITATIF", ""),
    ("Pack (nombre d'unités, film, identification)", "CONDITIONNEMENT", "QUALITATIF", ""),
    ("Aspect / couleur", "ORGANOLEPTIQUE", "QUALITATIF", ""),
    ("Goût", "ORGANOLEPTIQUE", "QUALITATIF", ""),
    ("Fonctionnement UV", "PROCESS", "QUALITATIF", ""),
    ("Microbiologie", "MICROBIOLOGIQUE", "QUALITATIF", ""),
    ("Conformité matière à réception", "MATIERE", "QUALITATIF", ""),
    ("Documents fournisseur", "DOCUMENTAIRE", "QUALITATIF", ""),
]


def _nombre(texte):
    import re
    from decimal import Decimal
    trouve = re.search(r"\d+(?:[.,]\d+)?", texte or "")
    return Decimal(trouve.group().replace(",", ".")) if trouve else None


def installer(apps, schema_editor):
    from apps.referentiel.models import contenance_depuis_format
    Activite = apps.get_model("industriel", "Activite")
    Usine = apps.get_model("industriel", "Usine")
    EtapeStandard = apps.get_model("industriel", "EtapeStandard")
    Circuit = apps.get_model("industriel", "Circuit")
    EtapeCircuit = apps.get_model("industriel", "EtapeCircuit")
    FamilleArticle = apps.get_model("referentiel", "FamilleArticle")
    Article = apps.get_model("referentiel", "Article")
    Depot = apps.get_model("stocks", "Depot")
    Lot = apps.get_model("qualite", "Lot")
    EtapeProduction = apps.get_model("production", "EtapeProduction")
    NatureCout = apps.get_model("couts", "NatureCout")
    ParametreQualite = apps.get_model("qualite", "ParametreQualite")

    activites = {}
    for code, designation in ACTIVITES:
        activite = Activite.objects.filter(code=code).first() or Activite.objects.create(code=code, designation=designation)
        activites[code] = activite
    for code, nom, codes in USINES:
        usine = Usine.objects.filter(code=code).first() or Usine.objects.create(code=code, nom=nom)
        usine.activites.add(*[activites[c] for c in codes])

    etapes = {}
    for code, libelle, phase, ordre, parent, description in ETAPES:
        etape = EtapeStandard.objects.filter(code=code).first()
        if etape is None:
            etape = EtapeStandard.objects.create(
                code=code, libelle=libelle, phase=phase, ordre_reference=ordre, description=description,
                sous_etape_de=etapes.get(parent),
            )
        etapes[code] = etape
    EtapeProduction.objects.filter(etape="EMBOUTEILLAGE").update(etape="REMPLISSAGE")

    for numero, (code_activite, sequence) in enumerate(CIRCUITS.items(), start=1):
        activite = activites[code_activite]
        if Circuit.objects.filter(activite=activite, article__isnull=True, ligne__isnull=True).exists():
            continue
        circuit = Circuit.objects.create(
            code=f"CIR-{code_activite}-REF", designation=f"Circuit de référence {activite.designation}",
            activite=activite, version=1, statut="VALIDE",
            observations="Circuit du document « Circuit complet de production ». Ordre des postes à confirmer par ligne.",
        )
        for ordre, (code_etape, obligatoire) in enumerate(sequence, start=1):
            EtapeCircuit.objects.create(circuit=circuit, etape=etapes[code_etape], ordre=ordre * 10, obligatoire=obligatoire)

    correspondance = {"EAU": "EAU", "JUS": "JUS", "YAO": "YAOURT"}
    for famille in FamilleArticle.objects.filter(activite__isnull=True):
        cle = "".join(c for c in famille.nom.upper() if c.isalpha())[:3]
        if cle in correspondance:
            famille.activite = activites[correspondance[cle]]
            famille.save(update_fields=["activite"])
    for article in Article.objects.filter(type_article="PRODUIT_FINI").select_related("famille", "format", "unite_vente"):
        champs = []
        if article.activite_id is None and article.famille_id and article.famille.activite_id:
            article.activite_id = article.famille.activite_id
            champs.append("activite")
        if article.contenance is None and article.format_id:
            article.contenance, article.unite_contenance = contenance_depuis_format(article.format.valeur)
            if article.contenance is not None:
                champs += ["contenance", "unite_contenance"]
        if article.unites_par_pack is None and article.unite_vente_id:
            nombre = _nombre(article.unite_vente.nom)
            article.unites_par_pack = int(nombre) if nombre else 1
            champs.append("unites_par_pack")
        if champs:
            article.save(update_fields=champs)
    for article in Article.objects.filter(mode_approvisionnement=""):
        article.mode_approvisionnement = (
            "ACHETE" if article.type_article in ("MATIERE_PREMIERE", "EMBALLAGE", "CONSOMMABLE")
            else "PROCESS" if article.type_article == "FLUIDE_PROCESS" else "FABRIQUE"
        )
        article.save(update_fields=["mode_approvisionnement"])

    types = {"Magasin principal": "MAGASIN_MATIERES", "Dépôt produits finis": "STOCK_USINE", "Quarantaine": "QUARANTAINE"}
    prefixes = {"MAGASIN_MATIERES": "MAG", "STOCK_USINE": "ST", "DEPOT_EXTERIEUR": "DEP", "QUARANTAINE": "QUA"}
    compteurs = {}
    for depot in Depot.objects.order_by("pk"):
        if depot.nom in types:
            depot.type_lieu = types[depot.nom]
        if not depot.code:
            prefixe = prefixes[depot.type_lieu]
            compteurs[prefixe] = compteurs.get(prefixe, 0) + 1
            while Depot.objects.filter(code=f"{prefixe}-{compteurs[prefixe]:03d}").exists():
                compteurs[prefixe] += 1
            depot.code = f"{prefixe}-{compteurs[prefixe]:03d}"
        depot.save(update_fields=["type_lieu", "code"])
    depot_pf = Depot.objects.filter(nom="Dépôt produits finis").first()
    if depot_pf is not None:
        Lot.objects.filter(depot__isnull=True).update(depot=depot_pf)

    rang = NatureCout.objects.count()
    for libelle, etape, categorie, economique, traitement, inducteur, justification in NATURES:
        if NatureCout.objects.filter(libelle=libelle).exists():
            continue
        rang += 1
        NatureCout.objects.create(
            code=f"NAT-{rang:03d}", libelle=libelle, etape=etapes.get(etape) if etape else None, categorie=categorie,
            categorie_economique=economique, traitement=traitement, inducteur=inducteur, justification=justification,
        )

    rang = ParametreQualite.objects.count()
    for libelle, famille, type_resultat, unite in PARAMETRES:
        if ParametreQualite.objects.filter(libelle=libelle).exists():
            continue
        rang += 1
        ParametreQualite.objects.create(code=f"PAR-{rang:03d}", libelle=libelle, famille=famille, type_resultat=type_resultat, unite=unite)


class Migration(migrations.Migration):

    dependencies = [
        ("industriel", "0001_initial"),
        ("core", "0003_notifications_anomalies"),
        ("referentiel", "0009_article_activite_article_activites_autorisees_and_more"),
        ("stocks", "0004_depot_activite_depot_articles_autorises_depot_code_and_more"),
        ("couts", "0003_charge_activite_charge_equipement_and_more"),
        ("qualite", "0003_nonconformite_lot_matiere_and_more"),
        ("production", "0007_sortiematiere_lot_matiere_and_more"),
    ]

    operations = [migrations.RunPython(installer, migrations.RunPython.noop)]
