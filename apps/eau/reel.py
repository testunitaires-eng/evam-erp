"""
Coût réel du mois de l'eau traitée et clôture (onglet « Scénario 3 mois »
du classeur, parties A à E).

    Volume = bouteilles conformes des OF du site clôturés dans le mois
             x contenance ÷ 1 000 (m³).
    Électricité : la facture du site (charges « Électricité ») répartie
             aux kW x heures de chaque équipement : forage, traitement,
             production (hors coût de l'eau, coût de la ligne).
    Forage (avant partage) = électricité forage + étalées forage + charges
             imputées au forage ; part du site eau = débitmètres.
    Traitement = électricité traitement + étalées + charges imputées.
    Charges au besoin (réparations, grosses réparations étalées) et
             exceptionnelles (valeurs résiduelles) : à part, hors
             comparaison avec le standard.
    Eau valorisée dans les OF = volume x standard en vigueur ; écart du
             mois = coût réel total - eau valorisée (les OF ne sont pas
             recalculés).
"""

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .calculs import CENTIME, CalculImpossible, _montant, _nombre, calcul_previsionnel
from .models import (
    Bloc, Categorie, ClotureMoisEau, Compteur, CoutStandardEau, ElementCout, Famille, ParametresEau, TypeCompteur,
    ValidationSansImputation, ValorisationEauOF, VersionElementCout, ajouter_mois, charges_imputees, mois_courant, mois_de,
    verifier_format_mois,
)
from .traitement import bornes_du_mois, heures_machine, synthese_mois, volume_compteur

ZERO = Decimal(0)


def _part(montant, total, valeur):
    return montant * valeur / total if total else ZERO


# ---------------------------------------------------------------------------
# A. Volumes et pertes
# ---------------------------------------------------------------------------

def ofs_du_mois(usine, mois):
    from apps.production.models import OrdreFabrication
    debut, fin = bornes_du_mois(mois)
    return OrdreFabrication.objects.filter(
        statut="CLOTURE", ligne__usine=usine, date_fin__date__gte=debut, date_fin__date__lte=fin,
    ).select_related("article").order_by("numero")


def volumes_du_mois(usine, mois, taux_rejet_tolere):
    """Bouteilles conformes et rejetées par format (OF clôturés du mois), volume, taux de rejet, pertes."""
    from apps.production.models import SuiviEau
    formats, par_of, alertes = {}, [], []

    def format_de(article):
        return formats.setdefault(article.pk, {
            "article": article, "conformes": ZERO, "rejetees": ZERO, "litres": ZERO, "litres_rejetes": ZERO,
        })

    for of in ofs_du_mois(usine, mois):
        litres_of, detail = ZERO, {}
        if not of.lots.exists():
            alertes.append(f"{of.numero} : aucun lot enregistré, quantité prévue retenue.")
        for article, quantite in of.quantites_par_format().items():
            if not article.contenance or article.unite_contenance != "L":
                alertes.append(f"{of.numero} : contenance en litres de {article.code} non renseignée, format ignoré.")
                continue
            bouteilles = article.en_unites(quantite)
            litres = bouteilles * article.contenance
            ligne = format_de(article)
            ligne["conformes"] += bouteilles
            ligne["litres"] += litres
            litres_of += litres
            detail[article.code] = litres
        suivi = SuiviEau.objects.filter(ordre_fabrication=of).first()
        if suivi is not None and suivi.bouteilles_rejetees and of.article.contenance and of.article.unite_contenance == "L":
            ligne = format_de(of.article)
            ligne["rejetees"] += suivi.bouteilles_rejetees
            ligne["litres_rejetes"] += suivi.bouteilles_rejetees * of.article.contenance
        par_of.append({"of": of, "volume_m3": litres_of / 1000, "litres_par_format": detail})

    if taux_rejet_tolere is None and any(f["rejetees"] for f in formats.values()):
        alertes.append("Taux de rejet toléré non paramétré : l'eau des bouteilles rejetées est comptée en perte normale.")
    lignes, rejete_normal, rejete_anormal = [], ZERO, ZERO
    for ligne in sorted(formats.values(), key=lambda l: l["article"].code):
        total = ligne["conformes"] + ligne["rejetees"]
        taux = ligne["rejetees"] / total if total else ZERO
        anormale = taux_rejet_tolere is not None and taux > taux_rejet_tolere
        if anormale:
            rejete_anormal += ligne["litres_rejetes"] / 1000
        else:
            rejete_normal += ligne["litres_rejetes"] / 1000
        lignes.append({
            "article": ligne["article"].code, "contenance_l": _nombre(ligne["article"].contenance),
            "bouteilles_conformes": _nombre(ligne["conformes"], 0), "bouteilles_rejetees": _nombre(ligne["rejetees"], 0),
            "volume_m3": _nombre(ligne["litres"] / 1000, 3), "eau_rejetee_m3": _nombre(ligne["litres_rejetes"] / 1000, 3),
            "taux_rejet": _nombre(taux, 6),
            "classement_rejet": ("Perte anormale" if anormale else "Perte normale") if ligne["rejetees"] else None,
        })
    volume = sum((l["litres"] for l in formats.values()), ZERO) / 1000
    return {
        "formats": lignes, "volume": volume, "rejete_normal": rejete_normal, "rejete_anormal": rejete_anormal,
        "par_of": par_of, "alertes": alertes,
    }


# ---------------------------------------------------------------------------
# C. Charges réelles
# ---------------------------------------------------------------------------

def _etalees(usine, mois):
    """{élément: (étalement du mois, valeur résiduelle du mois)} des éléments de la famille Étalée."""
    resultat = {}
    for element in ElementCout.objects.filter(usine=usine, famille=Famille.ETALEE).select_related("etape__sous_etape_de"):
        lots = list(element.installations.select_related("remplace"))
        if lots:
            etale = sum((lot.montant_etale(mois) for lot in lots), ZERO)
            residuel = sum((lot.valeur_residuelle for lot in lots if lot.remplace_id and lot.mois_installation == mois), ZERO)
        else:
            version = VersionElementCout.en_vigueur(mois, element=element)
            if version is not None:
                version.element = element
            etale, residuel = (version.montant_mensuel_avant_part() if version else ZERO), ZERO
        resultat[element] = (etale, residuel)
    return resultat


def _charges_imputees(usine, mois):
    """{élément: (courant, au besoin)} : charges du module Coûts rattachées à l'eau (hors électricité)."""
    from apps.couts.models import Charge
    debut_possible = ajouter_mois(mois, -240)
    resultat = {}
    charges = Charge.objects.filter(
        element_eau__usine=usine, periode__lte=mois, periode__gte=debut_possible,
    ).exclude(element_eau__categorie=Categorie.ELECTRICITE).select_related("element_eau__etape__sous_etape_de")
    for charge in charges:
        element = charge.element_eau
        courant, besoin = resultat.get(element, (ZERO, ZERO))
        if charge.duree_etalement_eau_mois:
            if charge.periode <= mois <= ajouter_mois(charge.periode, charge.duree_etalement_eau_mois - 1):
                besoin += Decimal(charge.montant) / charge.duree_etalement_eau_mois
        elif charge.periode == mois:
            if element.famille == Famille.AU_BESOIN:
                besoin += charge.montant
            else:
                courant += charge.montant
        resultat[element] = (courant, besoin)
    return resultat


def _electricite(usine, mois, heures):
    """Facture du site répartie aux kW x heures : {"total", "par_bloc" {FORAGE, TRAITEMENT, None}, "kwh" {...}}."""
    from django.db.models import Sum
    from apps.couts.models import Charge
    total = Charge.objects.filter(
        element_eau__usine=usine, element_eau__categorie=Categorie.ELECTRICITE, periode=mois,
    ).aggregate(t=Sum("montant"))["t"] or ZERO
    kwh = {Bloc.FORAGE: ZERO, Bloc.TRAITEMENT: ZERO, None: ZERO}
    for ligne in heures:
        if ligne["_exact"]["kw_heures"]:
            bloc = Bloc(ligne["bloc"]) if ligne["bloc"] else None
            kwh[bloc] += ligne["_exact"]["kw_heures"]
    total_kwh = sum(kwh.values(), ZERO)
    return {
        "total": total, "kwh": kwh, "total_kwh": total_kwh,
        "par_bloc": {bloc: _part(total, total_kwh, valeur) for bloc, valeur in kwh.items()},
    }


# ---------------------------------------------------------------------------
# Charges attendues
# ---------------------------------------------------------------------------

def charges_attendues(usine, mois):
    """Statut de chaque charge attendue du mois : IMPUTEE, VALIDEE_SANS_IMPUTATION ou MANQUANTE."""
    lignes = []
    for element in ElementCout.objects.filter(usine=usine, attendue_chaque_mois=True).order_by("ordre", "pk"):
        version = VersionElementCout.en_vigueur(mois, element=element)
        if version is not None and version.retire:
            continue
        validation = ValidationSansImputation.objects.filter(element=element, mois=mois).first()
        if charges_imputees(element, mois).exists():
            statut, motif = "IMPUTEE", ""
        elif validation is not None:
            statut, motif = "VALIDEE_SANS_IMPUTATION", validation.motif
        else:
            statut, motif = "MANQUANTE", ""
        lignes.append({"element": element.pk, "libelle": element.libelle, "statut": statut, "motif": motif})
    return lignes


# ---------------------------------------------------------------------------
# Calcul complet
# ---------------------------------------------------------------------------

def calcul_reel(usine, mois):
    verifier_format_mois(mois, "mois")
    alertes, bloquants = [], []
    parametres = ParametresEau.en_vigueur(mois, usine=usine)
    taux_tolere = parametres.taux_rejet_tolere_pct / 100 if parametres and parametres.taux_rejet_tolere_pct is not None else None

    # A. Volumes, partage du forage, pertes
    volumes = volumes_du_mois(usine, mois, taux_tolere)
    alertes += volumes["alertes"]
    volume = volumes["volume"]
    if not volume:
        bloquants.append("Aucune bouteille conforme sur les OF clôturés du mois : le coût au m³ ne peut pas être calculé.")
    traitement = synthese_mois(usine, mois)
    alertes += traitement["alertes"]
    partage = traitement["partage_forage"]
    part = traitement["_exact"]["part_site_eau"]
    if part is None:
        bloquants.append("Part du site eau dans le forage inconnue : relevez les débitmètres du mois.")
    capte_site = traitement["_exact"]["volume_site_eau"]

    # B. Heures machine, électricité
    heures = heures_machine(usine, mois)
    electricite = _electricite(usine, mois, heures)
    if electricite["total"] and not electricite["total_kwh"]:
        bloquants.append("Facture d'électricité imputée mais aucune heure machine (kW x heures) : elle ne peut pas être répartie.")

    # C. Charges
    prevu = {ligne["element"]: ligne["cout_mensuel"] for ligne in calcul_previsionnel(usine, mois)["charges"]}
    etalees, imputees = _etalees(usine, mois), _charges_imputees(usine, mois)
    blocs = (Bloc.FORAGE, Bloc.TRAITEMENT)
    courant = {bloc: electricite["par_bloc"][bloc] for bloc in blocs}
    besoin = {bloc: ZERO for bloc in blocs}
    exceptionnel = {bloc: ZERO for bloc in blocs}
    lignes = []
    for bloc in blocs:
        prevu_elec = sum((Decimal(prevu[e.pk]) for e in ElementCout.objects.filter(usine=usine, categorie=Categorie.ELECTRICITE)
                          if e.bloc == bloc and prevu.get(e.pk)), ZERO)
        lignes.append({
            "element": None, "bloc": bloc.value, "libelle": f"Électricité (facture du site) - part {bloc.label.lower()}",
            "famille": Famille.COURANTE, "nature": "courante", "prevu": _montant(prevu_elec),
            "reel_avant_part": _montant(electricite["par_bloc"][bloc]),
            "kw_heures": _nombre(electricite["kwh"][bloc], 3),
        })
    elements = ElementCout.objects.filter(usine=usine).exclude(categorie=Categorie.ELECTRICITE).select_related("etape__sous_etape_de")
    for element in elements.order_by("ordre", "pk"):
        bloc = element.bloc
        if element.famille == Famille.ETALEE:
            etale, residuel = etalees.get(element, (ZERO, ZERO))
            courant[bloc] += etale
            exceptionnel[bloc] += residuel
            montant_courant, montant_besoin, montant_exceptionnel = etale, ZERO, residuel
        else:
            montant_courant, montant_besoin = imputees.get(element, (ZERO, ZERO))
            montant_exceptionnel = ZERO
            courant[bloc] += montant_courant
            besoin[bloc] += montant_besoin
        if not (montant_courant or montant_besoin or montant_exceptionnel or prevu.get(element.pk)):
            continue
        lignes.append({
            "element": element.pk, "bloc": bloc.value, "libelle": element.libelle, "famille": element.famille,
            "prevu": prevu.get(element.pk), "reel_avant_part": _montant(montant_courant),
            "au_besoin_avant_part": _montant(montant_besoin) if montant_besoin else None,
            "exceptionnel_avant_part": _montant(montant_exceptionnel) if montant_exceptionnel else None,
        })

    # Charges attendues
    attendues = charges_attendues(usine, mois)
    manquantes = [l["libelle"] for l in attendues if l["statut"] == "MANQUANTE"]

    # D. Coût réel du mois
    part_calcul = part if part is not None else ZERO
    forage_avant = courant[Bloc.FORAGE]
    forage_site = forage_avant * part_calcul
    besoin_total = besoin[Bloc.FORAGE] * part_calcul + besoin[Bloc.TRAITEMENT]
    exceptionnel_total = exceptionnel[Bloc.FORAGE] * part_calcul + exceptionnel[Bloc.TRAITEMENT]
    cout_courant = forage_site + courant[Bloc.TRAITEMENT]
    cout_total = cout_courant + besoin_total + exceptionnel_total
    par_m3 = (lambda montant: montant / volume) if volume else (lambda montant: None)
    cout_m3, cout_m3_courant = par_m3(cout_total), par_m3(cout_courant)

    # E. Valorisation et écarts
    standard = CoutStandardEau.en_vigueur(mois, usine=usine)
    if standard is None:
        bloquants.append("Aucun coût standard validé en vigueur ce mois : l'eau des OF ne peut pas être valorisée.")
    standard_m3 = standard.cout_m3 if standard else None
    valorisation = volume * standard_m3 if standard_m3 is not None else None
    ecart_pct = lambda m3: (m3 / standard_m3 - 1) if m3 is not None and standard_m3 else None

    return {
        "usine": usine.code, "mois": mois,
        "volumes": {
            "formats": volumes["formats"], "volume_m3": _nombre(volume, 3),
            "eau_captee_site_m3": _nombre(capte_site, 3), "part_site_eau": partage["part_site_eau"],
            "taux_pertes_site": _nombre((capte_site - volume) / capte_site, 6) if capte_site else None,
            "pertes_rejets_normales_m3": _nombre(volumes["rejete_normal"], 3),
            "pertes_rejets_anormales_m3": _nombre(volumes["rejete_anormal"], 3),
            "pertes_declarees": traitement["pertes"],
        },
        "electricite": {
            "facture_site": _montant(electricite["total"]), "total_kw_heures": _nombre(electricite["total_kwh"], 3),
            "part_forage": _montant(electricite["par_bloc"][Bloc.FORAGE]),
            "part_traitement": _montant(electricite["par_bloc"][Bloc.TRAITEMENT]),
            "part_production_hors_eau": _montant(electricite["par_bloc"][None]),
        },
        "heures_machine": [{cle: valeur for cle, valeur in ligne.items() if cle != "_exact"} for ligne in heures],
        "charges": lignes,
        "charges_attendues": attendues,
        "synthese": {
            "cout_forage_avant_partage": _montant(forage_avant),
            "cout_forage_site_eau": _montant(forage_site),
            "cout_forage_autres_sites": _montant(forage_avant - forage_site) if part is not None else None,
            "cout_traitement": _montant(courant[Bloc.TRAITEMENT]),
            "cout_reel_courant": _montant(cout_courant),
            "charges_au_besoin": _montant(besoin_total),
            "charges_exceptionnelles": _montant(exceptionnel_total),
            "cout_reel_total": _montant(cout_total),
            "cout_m3": _montant(cout_m3) if cout_m3 is not None else None,
            "cout_m3_courant": _montant(cout_m3_courant) if cout_m3_courant is not None else None,
            "cout_standard_m3": _montant(standard_m3) if standard_m3 is not None else None,
            "eau_valorisee_of": _montant(valorisation) if valorisation is not None else None,
            "ecart_du_mois": _montant(cout_total - valorisation) if valorisation is not None else None,
            "valeur_perte_anormale": _montant(volumes["rejete_anormal"] * standard_m3) if standard_m3 is not None else None,
            "ecart_total_pct": _nombre(ecart_pct(cout_m3) * 100, 2) if ecart_pct(cout_m3) is not None else None,
            "ecart_courant_pct": _nombre(ecart_pct(cout_m3_courant) * 100, 2) if ecart_pct(cout_m3_courant) is not None else None,
        },
        "alertes": alertes,
        "bloquants": bloquants,
        "manquantes": manquantes,
        "_exact": {
            "volume": volume, "cout_courant": cout_courant, "cout_total": cout_total, "cout_m3": cout_m3,
            "cout_m3_courant": cout_m3_courant, "standard_m3": standard_m3, "valorisation": valorisation,
            "electricite_production": electricite["par_bloc"][None], "par_of": volumes["par_of"],
        },
    }


def sans_valeurs_exactes(calcul):
    return {cle: valeur for cle, valeur in calcul.items() if cle != "_exact"}


# ---------------------------------------------------------------------------
# Clôture
# ---------------------------------------------------------------------------

def _texte_volume(valeur):
    return format(Decimal(valeur).quantize(Decimal("0.001")), "f")


@transaction.atomic
def cloturer(usine, mois, utilisateur=None):
    """
    Clôture le mois : calcul du coût réel conservé, saisies figées, eau des
    OF du mois valorisée au standard (et leur coût réel recalculé),
    volumes des débitmètres reportés dans les relevés d'eau brute du module
    Coûts (s'ils n'y sont pas déjà).
    """
    from apps.couts.models import CoutReel, VolumeEauSite
    verifier_format_mois(mois, "mois")
    if ClotureMoisEau.objects.filter(usine=usine, mois=mois).exists():
        raise CalculImpossible(f"Le mois {mois} est déjà clôturé.")
    if mois >= mois_courant():
        raise CalculImpossible(f"Le mois {mois} n'est pas terminé.")
    precedent = ajouter_mois(mois, -1)
    if ClotureMoisEau.objects.filter(usine=usine).exists() and not ClotureMoisEau.objects.filter(usine=usine, mois=precedent).exists():
        raise CalculImpossible(f"Clôturez d'abord {precedent} (les mois se clôturent dans l'ordre).")
    calcul = calcul_reel(usine, mois)
    problemes = list(calcul["bloquants"])
    if calcul["manquantes"]:
        problemes.append("Charges attendues ni imputées ni validées sans imputation : " + ", ".join(calcul["manquantes"]) + ".")
    if problemes:
        raise CalculImpossible(" ".join(problemes))
    exact = calcul["_exact"]
    cloture = ClotureMoisEau.objects.create(
        usine=usine, mois=mois, volume_m3=exact["volume"].quantize(Decimal("0.001")),
        cout_reel_courant=exact["cout_courant"].quantize(CENTIME), cout_reel_total=exact["cout_total"].quantize(CENTIME),
        cout_m3=exact["cout_m3"].quantize(Decimal("0.0001")), cout_m3_courant=exact["cout_m3_courant"].quantize(Decimal("0.0001")),
        cout_standard_m3=exact["standard_m3"], valorisation_of=exact["valorisation"].quantize(CENTIME),
        ecart=(exact["cout_total"] - exact["valorisation"]).quantize(CENTIME),
        resultat=sans_valeurs_exactes(calcul), cloture_par=utilisateur,
    )
    for ligne in exact["par_of"]:
        of = ligne["of"]
        ValorisationEauOF.objects.create(
            cloture=cloture, ordre_fabrication=of, volume_m3=ligne["volume_m3"].quantize(Decimal("0.001")),
            cout_standard_m3=exact["standard_m3"],
            montant_eau=(ligne["volume_m3"] * exact["standard_m3"]).quantize(CENTIME),
            electricite_production=_part(exact["electricite_production"], exact["volume"], ligne["volume_m3"]).quantize(CENTIME),
        )
        cout, _ = CoutReel.objects.get_or_create(ordre_fabrication=of)
        cout.calculer()
    # Volumes captés par site (débitmètres) -> clé de répartition du forage du module Coûts.
    reportes = []
    for compteur in Compteur.objects.filter(usine=usine, type_compteur=TypeCompteur.DEBITMETRE, actif=True).select_related("site_desservi"):
        volume, _ = volume_compteur(compteur, mois)
        if volume is None:
            continue
        existant = VolumeEauSite.objects.filter(periode=mois, usine=compteur.site_desservi, activite__isnull=True).first()
        if existant is None:
            VolumeEauSite.objects.create(
                periode=mois, usine=compteur.site_desservi, volume_m3=volume, saisi_par=utilisateur,
                source=f"Débitmètre {compteur.code} (clôture du coût de l'eau)",
            )
            reportes.append(f"{compteur.site_desservi.code} : {_texte_volume(volume)} m³")
        elif existant.volume_m3 != volume:
            reportes.append(
                f"{compteur.site_desservi.code} : relevé d'eau brute déjà saisi ({_texte_volume(existant.volume_m3)} m³) "
                f"différent du débitmètre ({_texte_volume(volume)} m³), non modifié"
            )
    if reportes:
        cloture.resultat = {**cloture.resultat, "volumes_eau_brute_reportes": reportes}
        ClotureMoisEau.objects.filter(pk=cloture.pk).update(resultat=cloture.resultat)
    return cloture


def date_limite_cloture(usine, mois):
    """Jour limite pour imputer les charges du mois : le « jour de clôture » du mois suivant (10 par défaut)."""
    parametres = ParametresEau.en_vigueur(mois, usine=usine)
    jour = parametres.jour_cloture if parametres else 10
    annee, numero = (int(x) for x in ajouter_mois(mois, 1).split("-"))
    return date(annee, numero, jour)


def mois_a_cloturer(jour=None):
    """Le mois dont la date limite tombe dans le mois du jour donné (le mois précédent)."""
    return ajouter_mois(mois_de(jour or timezone.localdate()), -1)
