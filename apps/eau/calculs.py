"""
Calcul du coût standard prévisionnel de l'eau traitée (onglet « Calcul
coût eau » du classeur EVAM), pour un site et un mois, avec les
paramètres en vigueur ce mois-là :

    1. volume du mois = Σ bouteilles prévues x contenance ÷ 1 000 (m³) ;
    2. part du site eau dans le forage = m³ captés vers le site ÷ m³ captés au total ;
    3. coût mensuel de chaque élément selon sa famille, x part du site
       eau pour le bloc Forage (100 % pour le bloc Traitement) ;
    4. coût de l'eau = forage (part du site) + traitement ; coût au m³ =
       coût de l'eau ÷ volume.

Les montants sont gardés exacts pendant le calcul et arrondis seulement
à l'affichage (sinon 3 membranes à 20 833,33 feraient 62 499,99).
"""

from decimal import Decimal

from .models import (
    Bloc, CoutStandardEau, ElementCout, Famille, OrigineStandard, PrevisionCaptage, PrevisionVolume, VersionElementCout,
    verifier_format_mois,
)

CENTIME = Decimal("0.01")


def _montant(valeur):
    return None if valeur is None else str(valeur.quantize(CENTIME))


def _nombre(valeur, decimales=4):
    if valeur is None:
        return None
    texte = format(round(Decimal(valeur), decimales), "f")
    return texte.rstrip("0").rstrip(".") if "." in texte else texte


def _dernieres_versions(versions, cle):
    """Une version par clé : la plus récente déjà applicable (versions triées par clé puis mois décroissant)."""
    retenues = {}
    for version in versions:
        retenues.setdefault(getattr(version, cle), version)
    return retenues


class CalculImpossible(ValueError):
    pass


def calcul_previsionnel(usine, mois):
    """Le calcul complet, prêt à afficher (montants en texte, arrondis au centime) + valeurs exactes sous « _exact »."""
    verifier_format_mois(mois, "mois")
    alertes, bloquants = [], []

    # 1. Volume
    previsions = _dernieres_versions(
        PrevisionVolume.objects.filter(usine=usine, mois_application__lte=mois)
        .select_related("article").order_by("article_id", "-mois_application"),
        "article_id",
    )
    formats, volume = [], Decimal(0)
    for prevision in sorted(previsions.values(), key=lambda p: p.article.code):
        volume += prevision.volume_m3
        formats.append({
            "article": prevision.article.code, "bouteilles_par_mois": prevision.bouteilles_par_mois,
            "contenance_l": _nombre(prevision.article.contenance), "volume_m3": _nombre(prevision.volume_m3, 3),
        })
    if not volume:
        bloquants.append("Aucun volume prévu pour ce mois : renseignez les bouteilles prévues par format.")

    # 2. Partage du forage
    captage = PrevisionCaptage.en_vigueur(mois, usine=usine)
    part_site = captage.part_site_eau if captage else None

    # 3. Charges
    versions = _dernieres_versions(
        VersionElementCout.objects.filter(element__usine=usine, mois_application__lte=mois).order_by("element_id", "-mois_application"),
        "element_id",
    )
    lignes = []
    totaux = {Bloc.FORAGE: Decimal(0), Bloc.TRAITEMENT: Decimal(0)}
    somme_lignes = Decimal(0)   # contrôle : total des lignes = total de la synthèse par bloc
    elements = ElementCout.objects.filter(usine=usine).select_related("etape__sous_etape_de", "equipement")
    for element in elements:
        version = versions.get(element.pk)
        if version is not None and version.retire:
            continue
        bloc = element.bloc
        if bloc == Bloc.FORAGE:
            part = part_site
            if part is None:
                bloquants.append("Partage du forage non renseigné (m³ captés par site) : le coût du forage ne peut pas être calculé.")
                part = Decimal(0)
        else:
            part = Decimal(1)
        if version is None:
            cout = Decimal(0)
            if element.famille != Famille.AU_BESOIN:
                alertes.append(f"« {element.libelle} » n'est pas chiffré pour ce mois : compté 0.")
        else:
            version.element = element
            cout = version.montant_mensuel_avant_part() * part
        totaux[bloc] += cout
        somme_lignes += cout
        lignes.append({
            "element": element.pk, "bloc": bloc.value, "etape": element.etape.libelle, "libelle": element.libelle,
            "equipement": element.equipement.code if element.equipement_id else None,
            "famille": element.famille, "categorie": element.categorie, "a_indiquer": element.a_indiquer,
            "quantite": _nombre(version.quantite) if version else None, "unite": element.unite,
            "prix_unitaire": _nombre(version.prix_unitaire) if version else None,
            "frequence": _nombre(version.frequence) if version else None,
            "periode": (version.periode or None) if version else None,
            "duree_vie_mois": version.duree_vie_mois if version else None,
            "part_site": _nombre(part, 6), "cout_mensuel": _montant(cout),
            "cout_m3": _montant(cout / volume) if volume else None,
            "version_du": version.mois_application if version else None,
        })
    bloquants = list(dict.fromkeys(bloquants))

    # 4. Synthèse
    total = totaux[Bloc.FORAGE] + totaux[Bloc.TRAITEMENT]
    par_m3 = (lambda montant: montant / volume) if volume else (lambda montant: None)
    cout_m3 = par_m3(total)
    return {
        "usine": usine.code, "mois": mois,
        "volume": {"formats": formats, "total_m3": _nombre(volume, 3)},
        "partage_forage": {
            "volume_site_eau_m3": _nombre(captage.volume_site_eau_m3, 3) if captage else None,
            "volume_autres_sites_m3": _nombre(captage.volume_autres_sites_m3, 3) if captage else None,
            "part_site_eau": _nombre(part_site, 6),
        },
        "charges": lignes,
        "synthese": {
            "cout_forage": _montant(totaux[Bloc.FORAGE]), "cout_forage_m3": _montant(par_m3(totaux[Bloc.FORAGE])),
            "cout_traitement": _montant(totaux[Bloc.TRAITEMENT]), "cout_traitement_m3": _montant(par_m3(totaux[Bloc.TRAITEMENT])),
            "cout_mensuel": _montant(total), "cout_m3": _montant(cout_m3),
            "cout_litre": _nombre(cout_m3 / 1000, 6) if cout_m3 is not None else None,
            "controle": "OK" if total.quantize(CENTIME) == somme_lignes.quantize(CENTIME) else "Écart à vérifier",
        },
        "alertes": alertes, "bloquants": bloquants,
        "_exact": {"volume": volume, "forage": totaux[Bloc.FORAGE], "traitement": totaux[Bloc.TRAITEMENT], "total": total, "cout_m3": cout_m3},
    }


def sans_valeurs_exactes(calcul):
    return {cle: valeur for cle, valeur in calcul.items() if cle != "_exact"}


def proposer_standard(usine, mois_application, utilisateur=None):
    """Calcule le prévisionnel du mois et l'enregistre comme standard proposé (à valider par le contrôle de gestion)."""
    calcul = calcul_previsionnel(usine, mois_application)
    if calcul["bloquants"]:
        raise CalculImpossible(" ".join(calcul["bloquants"]))
    exact = calcul["_exact"]
    return CoutStandardEau.objects.create(
        usine=usine, mois_application=mois_application, origine=OrigineStandard.PREVISIONNEL,
        volume_m3=exact["volume"].quantize(Decimal("0.001")), cout_forage=exact["forage"].quantize(CENTIME),
        cout_traitement=exact["traitement"].quantize(CENTIME), cout_mensuel=exact["total"].quantize(CENTIME),
        cout_m3=exact["cout_m3"].quantize(Decimal("0.0001")), detail=sans_valeurs_exactes(calcul), propose_par=utilisateur,
    )
