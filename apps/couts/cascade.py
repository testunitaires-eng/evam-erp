"""
Moteur des coûts en cascade (voir les modèles NatureCout / Charge /
RepartitionCout dans models.py).

    calculer_periode("2026-09")   recalcule toute la période :
        1. chaque charge descend la cascade selon son élément de coût ;
        2. le coût réel des OF de la période est mis à jour ;
        3. le contrôle de non-double-compte est joint au résultat.

Exemple du document de référence :
    Forage 10 000 -> Eau 6 000 (m³ d'eau) -> OF-EAU-001 2 000 (m³ de l'OF)
    -> Eau 1 L 2 000 -> 6 000 bouteilles -> 0,3333 / bouteille.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q, Sum

from apps.production.models import OrdreFabrication
from .models import (
    Charge, CategorieCout, Inducteur, NiveauRepartition, RepartitionCout, StatutDonnee, StatutRepartition,
    UNITES_INDUCTEURS,
)

CENTIME = Decimal("0.01")


def bornes(periode):
    annee, mois = (int(x) for x in periode.split("-"))
    debut = date(annee, mois, 1)
    fin = date(annee + (mois == 12), mois % 12 + 1, 1)
    return debut, fin


def ofs_de_la_periode(periode, activite=None):
    """OF clôturés dans la période (leur réel est complet)."""
    debut, fin = bornes(periode)
    ofs = OrdreFabrication.objects.filter(statut="CLOTURE", date_fin__date__gte=debut, date_fin__date__lt=fin)
    if activite is not None:
        ofs = ofs.filter(article__activite=activite)
    return ofs.select_related("article").order_by("numero")


def valeur_inducteur(of, inducteur, etape=None):
    """
    Valeur de la clé pour un OF : (valeur | None, nature, source).
    nature : MESURE, CALCULE ou ESTIME. None = donnée absente : l'OF ne
    reçoit rien de cette charge (pas de valeur inventée).
    """
    from apps.couts.models import CoutMainOeuvre
    formats = of.quantites_par_format()   # {article: quantité bonne} (un ou plusieurs formats)
    if inducteur in (Inducteur.BOUTEILLES, Inducteur.PACKS, Inducteur.PALETTES, Inducteur.LITRES_PRODUITS):
        total, nature = Decimal(0), "CALCULE"
        for article, quantite in formats.items():
            valeur, nature_format, _ = valeur_format(article, quantite, inducteur)
            if valeur is None:
                return None, None, f"donnée manquante pour {article.code} (contenance ou packs par palette)"
            total += valeur
        return total, nature, "quantités produites bonnes de chaque format"
    if inducteur == Inducteur.VOLUME_EAU_M3:
        volume = of.volume_eau()
        if volume["litres"] is None:
            return None, None, "volume d'eau inconnu"
        source = "suivi eau (mesuré)" if volume["statut"] == "MESURE" else "consommation d'eau traitée"
        return Decimal(volume["litres"]) / Decimal(1000), volume["statut"], source
    if inducteur in (Inducteur.HEURES_MACHINE, Inducteur.KWH):
        etapes = of.etapes.all()
        if etape is not None:
            etapes = etapes.filter(etape=etape.code)
        total, trouve, estime = Decimal(0), False, False
        for saisie in etapes:
            if inducteur == Inducteur.HEURES_MACHINE:
                heures = saisie.heures_machine_effectives
                if heures is not None:
                    total += heures
                    trouve = True
            elif saisie.energie_kwh is not None:
                total += Decimal(saisie.energie_kwh)
                trouve = True
                estime = estime or not saisie.energie_mesuree
        if not trouve:
            return None, None, "aucune saisie par étape"
        if inducteur == Inducteur.KWH:
            return total, "ESTIME" if estime else "MESURE", "kWh saisis par étape"
        return total, "MESURE", "heures machine saisies par étape"
    if inducteur == Inducteur.HEURES_MO:
        heures = CoutMainOeuvre.objects.filter(ordre_fabrication=of).aggregate(t=Sum("heures"))["t"]
        return (Decimal(heures), "MESURE", "heures de main-d'œuvre de l'OF") if heures else (None, None, "aucune heure")
    if inducteur == Inducteur.ANALYSES_PONDEREES:
        from apps.qualite.models import ResultatControle
        resultats = ResultatControle.objects.filter(
            Q(ordre_fabrication=of) | Q(lot__ordre_fabrication=of), statut__in=("CONFORME", "NON_CONFORME"),
        )
        if etape is not None:
            resultats = resultats.filter(etape=etape)
        poids = resultats.aggregate(t=Sum("point__parametre__poids_analyse"))["t"]
        return (Decimal(poids), "CALCULE", "analyses réalisées x poids") if poids else (None, None, "aucune analyse")
    if inducteur == Inducteur.TEMPS_CHANGEMENT_SERIE:
        total = Decimal(0)
        for changement in of.changements_serie.all():
            total += Decimal(changement.duree_arret_min) + Decimal(changement.duree_nettoyage_min) + Decimal(changement.duree_reglage_min)
        return (total, "MESURE", "durées des changements de série de l'OF") if total else (None, None, "aucun changement de série")
    return None, None, "inducteur non applicable à un OF"


SOURCE_CHANGEMENT_SERIE = "Changement de série n° "


def charges_changements_serie(periode):
    """
    Le coût réel du nettoyage saisi sur un changement de série devient une
    charge DIRECTE de l'OF concerné (« direct à la série »). Recalculé à
    chaque calcul de période : modification ou suppression suivies.
    """
    from apps.industriel.models import EtapeStandard
    from .models import CategorieEconomique, NatureCout, Traitement
    nature, _ = NatureCout.objects.get_or_create(
        libelle="Nettoyage de changement de série", categorie=CategorieCout.PRODUCTION,
        defaults={
            "categorie_economique": CategorieEconomique.PRODUITS_TRAITEMENT, "traitement": Traitement.DIRECT,
            "inducteur": Inducteur.AUCUN, "etape": None,
            "justification": "Direct à la série : coût réel saisi sur l'événement de changement de série.",
        },
    )
    attendues = {}
    for of in ofs_de_la_periode(periode):
        for changement in of.changements_serie.filter(cout_nettoyage__gt=0):
            attendues[f"{SOURCE_CHANGEMENT_SERIE}{changement.pk}"] = (of, changement.cout_nettoyage)
    existantes = {c.source: c for c in Charge.objects.filter(periode=periode, nature=nature, source__startswith=SOURCE_CHANGEMENT_SERIE)}
    for source, charge in existantes.items():
        if source not in attendues:
            charge.delete()
    for source, (of, montant) in attendues.items():
        charge = existantes.get(source)
        if charge is None:
            Charge.objects.create(nature=nature, periode=periode, montant=montant, ordre_fabrication=of, source=source)
        elif charge.montant != montant:
            charge.montant = montant
            charge.save()


def valeur_format(article, quantite, inducteur):
    """Valeur d'un inducteur de volume pour un format : (valeur | None, nature, libellé)."""
    if inducteur == Inducteur.BOUTEILLES:
        return article.en_unites(quantite), "CALCULE", "bouteilles / pots"
    if inducteur == Inducteur.PACKS:
        return article.en_packs(quantite), "CALCULE", "packs"
    if inducteur == Inducteur.PALETTES:
        return article.en_palettes(quantite), "CALCULE", "palettes"
    if article.unite_contenance == "L" and article.contenance:
        return article.en_contenance(quantite), "CALCULE", "litres"
    return None, None, "litres"


def cle_entre_formats(formats, inducteur):
    """
    Clé de ventilation de la part d'un OF entre ses formats : l'inducteur de
    la charge s'il se mesure par format (bouteilles, packs, palettes,
    litres) ; sinon les litres produits (volume réellement traité), à défaut
    les bouteilles / pots. Retourne ([(article, valeur)], libellé).
    """
    if inducteur in (Inducteur.BOUTEILLES, Inducteur.PACKS, Inducteur.PALETTES, Inducteur.LITRES_PRODUITS):
        parts = [(article, valeur_format(article, quantite, inducteur)[0]) for article, quantite in formats.items()]
        if all(valeur for _, valeur in parts):
            return parts, valeur_format(next(iter(formats)), 1, inducteur)[2]
    litres = [(article, valeur_format(article, quantite, Inducteur.LITRES_PRODUITS)[0]) for article, quantite in formats.items()]
    if all(valeur for _, valeur in litres):
        return litres, "litres produits"
    return [(article, article.en_unites(quantite)) for article, quantite in formats.items()], "bouteilles / pots produits"


def ventiler(montant, parts):
    """
    Répartit `montant` selon [(cible, valeur)] au centime près ; l'écart
    d'arrondi va à la plus grosse part : la somme est EXACTEMENT le montant.
    """
    total = sum((valeur for _, valeur in parts), Decimal(0))
    resultat = []
    for cible, valeur in parts:
        resultat.append([cible, valeur, (Decimal(montant) * valeur / total).quantize(CENTIME, ROUND_HALF_UP)])
    ecart = Decimal(montant) - sum((ligne[2] for ligne in resultat), Decimal(0))
    if ecart and resultat:
        max(resultat, key=lambda ligne: ligne[1])[2] += ecart
    return total, resultat


def _statut(charge, nature_cle=None, direct=False):
    if charge.statut_donnee == StatutDonnee.ESTIME or nature_cle == "ESTIME":
        return "ESTIME"
    return "REEL" if direct else "REPARTI"


def _ligne(charge, niveau, montant, quote_part, parent=None, **champs):
    return RepartitionCout.objects.create(
        charge=charge, parent=parent, niveau=niveau, montant=montant, quote_part=quote_part,
        inducteur=champs.pop("inducteur", charge.nature.inducteur),
        unite_cle=champs.pop("unite_cle", UNITES_INDUCTEURS.get(charge.nature.inducteur, "")),
        etape=charge.nature.etape, source=champs.pop("source", charge.source), **champs,
    )


def _descendre_au_produit(ligne_of):
    """
    OF -> produit / format -> pack -> unité. Un seul format : la part de l'OF
    va entière au produit. Plusieurs formats : ventilée entre eux selon
    l'inducteur de la charge (sinon les litres produits), sans double compte.
    """
    of = ligne_of.ordre_fabrication
    formats = of.quantites_par_format()
    if len(formats) == 1:
        repartition, libelle = [(next(iter(formats)), ligne_of.valeur_cle_part or Decimal(1))], None
        total, ventilation = None, [[repartition[0][0], repartition[0][1], ligne_of.montant]]
    else:
        repartition, libelle = cle_entre_formats(formats, ligne_of.inducteur)
        total, ventilation = ventiler(ligne_of.montant, repartition)
    lignes = []
    for article, valeur, montant in ventilation:
        quantite = formats[article]
        unites = article.en_unites(quantite)
        packs = article.en_packs(quantite)
        lignes.append(_ligne(
            ligne_of.charge, NiveauRepartition.PRODUIT, montant, (valeur / total) if total else Decimal(1), parent=ligne_of,
            activite=ligne_of.activite, ordre_fabrication=of, article=article,
            valeur_cle_totale=total if total else ligne_of.valeur_cle_part, valeur_cle_part=valeur if total else ligne_of.valeur_cle_part,
            quantite_produite=quantite,
            cout_par_unite=(montant / unites) if unites else None,
            cout_par_pack=(montant / packs) if packs else None,
            statut=ligne_of.statut, inducteur=ligne_of.inducteur,
            unite_cle=libelle or ligne_of.unite_cle,
            justification=(
                (f"OF à plusieurs formats : part ventilée selon les {libelle}. " if libelle else "")
                + f"{article.code} : {unites.normalize()} unités, {packs.normalize()} packs de {article.unites_par_pack or 1} "
                f"-> {montant} ramené au pack puis à l'unité."
            ),
        ))
    return lignes


def _repartir_production(charge):
    from apps.industriel.models import Activite
    nature, periode = charge.nature, charge.periode
    inducteur, etape = nature.inducteur, nature.etape

    if charge.ordre_fabrication_id:
        of = charge.ordre_fabrication
        ligne = _ligne(
            charge, NiveauRepartition.OF, charge.montant, Decimal(1), activite=of.activite, ordre_fabrication=of,
            statut=_statut(charge, direct=True), justification="Charge identifiable directement à l'OF : aucune répartition.",
        )
        _descendre_au_produit(ligne)
        return StatutRepartition.REPARTIE, ""

    # 1. Niveau activité.
    if charge.activite_id:
        lignes_activite = [_ligne(
            charge, NiveauRepartition.ACTIVITE, charge.montant, Decimal(1), activite=charge.activite,
            statut=_statut(charge, direct=True),
            justification=(
                f"Équipement dédié {charge.equipement.code} : charge directe de l'activité."
                if charge.equipement_id else "Charge propre à l'activité."
            ),
        )]
    else:
        parts, natures = [], set()
        for activite in Activite.objects.filter(actif=True):
            total = Decimal(0)
            for of in ofs_de_la_periode(periode, activite):
                valeur, nature_cle, _ = valeur_inducteur(of, inducteur, etape)
                if valeur:
                    total += valeur
                    natures.add(nature_cle)
            if total > 0:
                parts.append((activite, total))
        if not parts:
            return StatutRepartition.NON_REPARTIE, (
                f"Aucune valeur de « {Inducteur(inducteur).label} » sur les OF clôturés de {periode} : "
                "pas de clé défendable, la charge reste non répartie."
            )
        total, ventilation = ventiler(charge.montant, parts)
        lignes_activite = [
            _ligne(
                charge, NiveauRepartition.ACTIVITE, montant, valeur / total, activite=activite,
                valeur_cle_totale=total, valeur_cle_part=valeur,
                statut=_statut(charge, "ESTIME" if "ESTIME" in natures else None),
                justification=f"Charge commune répartie entre activités au prorata de : {Inducteur(inducteur).label}.",
            )
            for activite, valeur, montant in ventilation
        ]

    # 2. Niveau OF, puis produit / pack / unité.
    restes = []
    for ligne_activite in lignes_activite:
        parts = []
        for of in ofs_de_la_periode(periode, ligne_activite.activite):
            valeur, nature_cle, source = valeur_inducteur(of, inducteur, etape)
            if valeur:
                parts.append(((of, nature_cle, source), valeur))
        if inducteur == Inducteur.AUCUN or not parts:
            restes.append(ligne_activite.activite.code)
            continue
        total, ventilation = ventiler(ligne_activite.montant, parts)
        for (of, nature_cle, source), valeur, montant in ventilation:
            ligne_of = _ligne(
                charge, NiveauRepartition.OF, montant, valeur / total, parent=ligne_activite,
                activite=ligne_activite.activite, ordre_fabrication=of,
                valeur_cle_totale=total, valeur_cle_part=valeur, statut=_statut(charge, nature_cle),
                source=f"{charge.source} ; clé : {source}".strip(" ;"),
                justification=f"Part de l'activité répartie entre ses OF au prorata de : {Inducteur(inducteur).label}.",
            )
            _descendre_au_produit(ligne_of)
    if restes and len(restes) == len(lignes_activite):
        return StatutRepartition.PARTIELLE, (
            "Imputée à l'activité " + ", ".join(restes) + " mais pas aux OF : aucune valeur de l'inducteur sur ses OF clôturés."
        )
    if restes:
        return StatutRepartition.PARTIELLE, "Non descendue aux OF pour : " + ", ".join(restes) + " (inducteur sans valeur)."
    return StatutRepartition.REPARTIE, ""


def palettes_jours(article, periode):
    """Palettes-jours de stock produit fini (stock usine + dépôts) sur la période ; None si le format de palette est inconnu."""
    from apps.stocks.models import MouvementStock, TypeLieu
    if not article.packs_par_palette:
        return None
    debut, fin = bornes(periode)
    mouvements = MouvementStock.objects.filter(
        article=article, depot__type_lieu__in=(TypeLieu.STOCK_USINE, TypeLieu.DEPOT_EXTERIEUR), date_mouvement__date__lt=fin,
    ).values_list("date_mouvement", "type_mouvement", "quantite")
    par_jour, stock = {}, Decimal(0)
    for quand, type_mouvement, quantite in mouvements:
        signe = -1 if type_mouvement == "SORTIE" else 1
        jour = quand.date()
        if jour < debut:
            stock += signe * Decimal(quantite)
        else:
            par_jour[jour] = par_jour.get(jour, Decimal(0)) + signe * Decimal(quantite)
    cumul, jour = Decimal(0), debut
    while jour < fin:
        stock += par_jour.get(jour, Decimal(0))
        cumul += max(stock, Decimal(0))
        jour += timedelta(days=1)
    return article.en_palettes(cumul) if cumul else Decimal(0)


def quantites_livrees(periode, tournee=None):
    """{article: unités livrées} des bons de livraison livrés dans la période (ou de la tournée)."""
    from apps.distribution.models import BonLivraison
    debut, fin = bornes(periode)
    bls = BonLivraison.objects.filter(statut="LIVREE")
    bls = bls.filter(tournee=tournee) if tournee is not None else bls.filter(date_livraison__date__gte=debut, date_livraison__date__lt=fin)
    resultat = {}
    for bl in bls.select_related("commande"):
        for ligne in bl.commande.lignes.select_related("article"):
            resultat[ligne.article] = resultat.get(ligne.article, Decimal(0)) + ligne.article.en_unites(ligne.quantite)
    return resultat


def _repartir_hors_production(charge):
    """Stockage et distribution : répartis par produit, hors coût de production."""
    from apps.distribution.models import Tournee
    nature, periode = charge.nature, charge.periode
    inducteur = nature.inducteur
    parts, source = [], ""
    if inducteur == Inducteur.PALETTES_JOURS:
        from apps.referentiel.models import Article
        articles = Article.objects.filter(type_article="PRODUIT_FINI")
        if charge.activite_id:
            articles = articles.filter(activite=charge.activite)
        parts = [(article, valeur) for article in articles for valeur in [palettes_jours(article, periode)] if valeur]
        source = "stock quotidien des lieux produits finis / packs par palette"
    elif inducteur in (Inducteur.QUANTITE_LIVREE, Inducteur.PALETTES_LIVREES, Inducteur.LITRES_LIVRES):
        # Q59 : coût de tournée réparti selon une clé justifiable (unités, palettes ou volume livrés).
        livrees = quantites_livrees(periode, charge.tournee if charge.tournee_id else None)
        parts = []
        for article, unites in livrees.items():
            if not unites or (charge.activite_id and article.activite_id != charge.activite_id):
                continue
            quantite = unites / article.facteur_unites
            valeur = (unites if inducteur == Inducteur.QUANTITE_LIVREE
                      else article.en_palettes(quantite) if inducteur == Inducteur.PALETTES_LIVREES
                      else article.en_contenance(quantite) if article.unite_contenance == "L" else None)
            if valeur:
                parts.append((article, valeur))
        source = f"bons de livraison livrés ({UNITES_INDUCTEURS[inducteur]})"
    elif inducteur == Inducteur.KM:
        debut, fin = bornes(periode)
        tournees = [charge.tournee] if charge.tournee_id else list(Tournee.objects.filter(date_tournee__gte=debut, date_tournee__lt=fin))
        cumul = {}
        km_tournees = [(t, t.kilometres) for t in tournees if t.kilometres]
        total_km = sum((km for _, km in km_tournees), Decimal(0))
        if total_km:
            for tournee, km in km_tournees:
                poids = km / total_km
                livrees = quantites_livrees(periode, tournee)
                total_q = sum(livrees.values(), Decimal(0))
                for article, q in livrees.items():
                    if total_q:
                        cumul[article] = cumul.get(article, Decimal(0)) + Decimal(poids) * q / total_q
        parts = [(article, valeur) for article, valeur in cumul.items() if valeur]
        source = "km des tournées, puis quantité livrée dans chaque tournée"
    if not parts:
        return StatutRepartition.NON_REPARTIE, f"Aucune valeur de « {Inducteur(inducteur).label} » pour {periode} : charge non répartie."
    total, ventilation = ventiler(charge.montant, parts)
    produites = {}
    for of in ofs_de_la_periode(periode):
        for article, quantite in of.quantites_par_format().items():
            produites[article.pk] = produites.get(article.pk, Decimal(0)) + quantite
    for article, valeur, montant in ventilation:
        quantite = produites.get(article.pk)
        unites = article.en_unites(quantite) if quantite else None
        _ligne(
            charge, NiveauRepartition.ARTICLE, montant, valeur / total, activite=article.activite, article=article,
            valeur_cle_totale=total, valeur_cle_part=valeur, statut=_statut(charge),
            quantite_produite=quantite, cout_par_unite=(montant / unites) if unites else None,
            cout_par_pack=(montant / article.en_packs(quantite)) if quantite else None,
            source=f"{charge.source} ; clé : {source}".strip(" ;"),
            justification=(
                f"{nature.get_categorie_display()} : hors coût de production, réparti par produit au prorata de "
                f"{Inducteur(inducteur).label} ; ramené aux unités produites de la période."
            ),
        )
    return StatutRepartition.REPARTIE, ""


def repartir_charge(charge):
    RepartitionCout.objects.filter(charge=charge).delete()
    categorie = charge.nature.categorie
    if categorie == CategorieCout.HORS_COUT:
        statut, motif = StatutRepartition.NON_REPARTIE, "Frais généraux : non incorporés au coût de revient (règle validée)."
    elif categorie == CategorieCout.PRODUCTION:
        statut, motif = _repartir_production(charge)
    else:
        statut, motif = _repartir_hors_production(charge)
    Charge.objects.filter(pk=charge.pk).update(statut_repartition=statut, motif_non_repartition=motif)
    charge.statut_repartition, charge.motif_non_repartition = statut, motif
    return statut


def controle_non_double_compte(periode):
    """
    « Les répartitions successives ventilent la même charge : elles ne
    créent pas de nouveaux coûts. » Vérifie chaque niveau ; retourne la
    liste des écarts (vide = conforme).
    """
    anomalies = []
    for charge in Charge.objects.filter(periode=periode):
        racines = charge.repartitions.filter(parent__isnull=True)
        if racines.exists():
            total = racines.aggregate(t=Sum("montant"))["t"]
            if charge.statut_repartition == StatutRepartition.REPARTIE and total != charge.montant:
                anomalies.append(f"{charge.numero} : {total} réparti pour {charge.montant}.")
            if total > charge.montant:
                anomalies.append(f"{charge.numero} : plus réparti ({total}) que son montant ({charge.montant}).")
        for parent in charge.repartitions.filter(enfants__isnull=False).distinct():
            somme = parent.enfants.aggregate(t=Sum("montant"))["t"]
            if somme != parent.montant:
                anomalies.append(f"{charge.numero} / {parent.get_niveau_display()} : enfants {somme} pour {parent.montant}.")
    return anomalies


@transaction.atomic
def calculer_periode(periode):
    """Recalcule toute la cascade de la période, puis le coût réel des OF concernés."""
    from .models import CoutReel
    resultat = {"periode": periode, "charges": 0, "repartie": 0, "partielle": 0, "non_repartie": 0}
    charges_changements_serie(periode)
    for charge in Charge.objects.filter(periode=periode).select_related("nature", "nature__etape"):
        statut = repartir_charge(charge)
        resultat["charges"] += 1
        cle = {"REPARTIE": "repartie", "PARTIELLE": "partielle", "NON_REPARTIE": "non_repartie"}.get(statut)
        if cle:
            resultat[cle] += 1
    ofs = set(ofs_de_la_periode(periode)) | set(
        OrdreFabrication.objects.filter(charges_directes__periode=periode).distinct()
    )
    for of in ofs:
        cout, _ = CoutReel.objects.get_or_create(ordre_fabrication=of)
        cout.calculer()
    resultat["ofs_recalcules"] = len(ofs)
    resultat["anomalies_double_compte"] = controle_non_double_compte(periode)
    return resultat


def generer_amortissements(periode, utilisateur=None):
    """
    Charges d'amortissement de la période à partir des équipements
    (valeur / durée), rattachées à l'étape de leur poste : dédiées à
    l'activité de l'équipement, sinon communes (réparties au volume d'eau
    en amont, aux heures machine ailleurs). Idempotent.
    """
    from apps.industriel.models import Equipement, PhaseEtape
    from .models import CategorieEconomique, NatureCout, Traitement
    debut, fin = bornes(periode)
    creees = []
    for equipement in Equipement.objects.filter(actif=True, valeur_acquisition__gt=0, duree_amortissement_mois__gt=0):
        if equipement.date_mise_en_service and equipement.date_mise_en_service >= fin:
            continue
        if equipement.date_mise_en_service:
            mois = (debut.year - equipement.date_mise_en_service.year) * 12 + debut.month - equipement.date_mise_en_service.month
            if mois >= equipement.duree_amortissement_mois:
                continue
        etape = equipement.poste.etape if equipement.poste_id else None
        amont = etape is not None and etape.phase == PhaseEtape.AMONT
        inducteur = equipement.inducteur_amortissement or (Inducteur.VOLUME_EAU_M3 if amont else Inducteur.HEURES_MACHINE)
        # Une seule charge par équipement, même s'il réalise plusieurs postes (pas de double compte, Q56).
        nature, _ = NatureCout.objects.get_or_create(
            libelle=f"Amortissement {etape.libelle if etape else 'équipements'} ({Inducteur(inducteur).label})", etape=etape,
            categorie=CategorieCout.PRODUCTION,
            defaults={
                "categorie_economique": CategorieEconomique.AMORTISSEMENT, "traitement": Traitement.INDIRECT,
                "inducteur": inducteur,
                "justification": "Amortissement mensuel imputé selon l'usage réel de l'équipement (inducteur paramétré).",
            },
        )
        source = f"Amortissement {equipement.code}"
        if Charge.objects.filter(periode=periode, equipement=equipement, nature=nature, source=source).exists():
            continue
        creees.append(Charge.objects.create(
            nature=nature, periode=periode, equipement=equipement, activite=equipement.activite,
            montant=Decimal(equipement.amortissement_mensuel).quantize(CENTIME), source=source, saisi_par=utilisateur,
        ))
    return creees


def cout_eau_traitee(periode):
    """
    Coût de l'eau traitée par activité (captage + traitement + stockage
    process) : charges amont imputées à l'activité / litres utilisés par
    ses OF. Sert à valoriser l'eau traitée consommée dans les recettes.
    """
    from apps.industriel.models import Activite, PhaseEtape
    resultat = []
    for activite in Activite.objects.filter(actif=True):
        montant = RepartitionCout.objects.filter(
            charge__periode=periode, niveau=NiveauRepartition.ACTIVITE, activite=activite,
            charge__nature__etape__phase=PhaseEtape.AMONT,
        ).aggregate(t=Sum("montant"))["t"] or Decimal(0)
        litres = Decimal(0)
        for of in ofs_de_la_periode(periode, activite):
            volume = of.volume_eau()["litres"]
            if volume:
                litres += volume
        resultat.append({
            "activite": activite.code, "charges_amont": montant, "litres": litres,
            "cout_par_litre": (montant / litres) if litres else None,
            "cout_par_m3": (montant / litres * 1000) if litres else None,
        })
    return resultat


def cout_revient(periode):
    """
    Coût de revient par OF de la période (production) et par produit
    (production + stockage + distribution = coût de revient complet).
    """
    from apps.industriel.models import EtapeStandard
    from .models import CoutReel
    par_of, par_article = [], {}
    for of in ofs_de_la_periode(periode):
        cout, _ = CoutReel.objects.get_or_create(ordre_fabrication=of)
        article = of.article
        quantite = of.quantite_produite_bonne
        unites = article.en_unites(quantite)
        packs = article.en_packs(quantite)
        par_etape, changement_serie = {}, Decimal(0)
        for ligne in RepartitionCout.objects.filter(ordre_fabrication=of, niveau=NiveauRepartition.PRODUIT).select_related("etape", "charge__nature"):
            libelle = ligne.etape.libelle if ligne.etape_id else "Sans étape"
            par_etape[libelle] = par_etape.get(libelle, Decimal(0)) + ligne.montant
            if ligne.charge.source.startswith(SOURCE_CHANGEMENT_SERIE) or ligne.charge.nature.inducteur == Inducteur.TEMPS_CHANGEMENT_SERIE:
                changement_serie += ligne.montant
        total = cout.cout_total
        ventilation = cout.ventilation_par_format()
        par_of.append({
            "of": of.numero, "article": article.code, "quantite_produite": quantite, "unites": unites, "packs": packs,
            "matieres": cout.cout_matiere_total, "main_oeuvre": cout.cout_main_oeuvre_total,
            "charges_reparties": cout.cout_charges_reparties, "charges_par_etape": par_etape,
            "dont_changement_serie": changement_serie,
            "energie_et_amortissement_anciens": cout.cout_energie_total + cout.cout_amortissement_total,
            "cout_production": total,
            "cout_par_unite": (total / unites) if unites else None,
            "cout_par_pack": (total / packs) if packs else None,
            "formats": [
                {"article": l["article"].code, "quantite": l["quantite"], "unites": l["unites"], "cout": l["cout"],
                 "cout_par_unite": (l["cout"] / l["unites"]) if l["unites"] else None}
                for l in ventilation
            ],
        })
        for l in ventilation:
            donnees = par_article.setdefault(l["article"].pk, {
                "article": l["article"].code, "designation": l["article"].designation, "unites": Decimal(0),
                "production": Decimal(0), "stockage": Decimal(0), "distribution": Decimal(0),
            })
            donnees["unites"] += l["unites"]
            donnees["production"] += l["cout"]
    for ligne in RepartitionCout.objects.filter(charge__periode=periode, niveau=NiveauRepartition.ARTICLE).select_related("article", "charge__nature"):
        donnees = par_article.setdefault(ligne.article_id, {
            "article": ligne.article.code, "designation": ligne.article.designation, "unites": Decimal(0),
            "production": Decimal(0), "stockage": Decimal(0), "distribution": Decimal(0),
        })
        cle = "stockage" if ligne.charge.nature.categorie == CategorieCout.STOCKAGE else "distribution"
        donnees[cle] += ligne.montant
    for donnees in par_article.values():
        unites = donnees["unites"]
        for cle in ("production", "stockage", "distribution"):
            donnees[f"{cle}_par_unite"] = (donnees[cle] / unites) if unites else None
        complet = donnees["production"] + donnees["stockage"] + donnees["distribution"]
        donnees["cout_revient_complet"] = complet
        donnees["cout_revient_complet_par_unite"] = (complet / unites) if unites else None
    non_reparties = Charge.objects.filter(periode=periode, statut_repartition__in=("NON_REPARTIE", "PARTIELLE"))
    return {
        "periode": periode, "ofs": par_of, "produits": list(par_article.values()),
        "charges_non_reparties": [
            {"charge": c.numero, "nature": c.nature.libelle, "montant": c.montant, "statut": c.statut_repartition,
             "motif": c.motif_non_repartition} for c in non_reparties.select_related("nature")
        ],
        "etapes": list(EtapeStandard.objects.values_list("libelle", flat=True)),
    }
