"""
Synthèse mensuelle des saisies du traitement de l'eau (sans aucun coût :
consultable par les techniciens).

- Volume d'un compteur sur le mois = dernier index du mois - dernier
  index du mois précédent (à défaut, le premier index du mois : alerte).
- Part réelle du site eau dans le forage = m³ des débitmètres vers le
  site eau ÷ m³ de tous les débitmètres du forage.
- Heures machine = heures standard de chaque jour de marche du mois
  (jusqu'à aujourd'hui pour le mois en cours) - exceptions saisies sur
  l'équipement ou sur sa ligne entière, jamais en dessous de 0.
"""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from .models import (
    JOURS_DE_LA_SEMAINE, CaracteristiquesEquipement, Compteur, ExceptionHeures, PerteEau, ReleveCompteur, TypeCompteur,
    TypePerte, bloc_de_l_equipement, verifier_format_mois,
)


def bornes_du_mois(mois):
    annee, numero = (int(x) for x in mois.split("-"))
    return date(annee, numero, 1), date(annee, numero, calendar.monthrange(annee, numero)[1])


def _texte(valeur, decimales=3):
    if valeur is None:
        return None
    texte = format(round(Decimal(valeur), decimales), "f")
    return texte.rstrip("0").rstrip(".") if "." in texte else texte


def volume_compteur(compteur, mois):
    """(volume en m³ ou None, alerte ou None)."""
    debut, fin = bornes_du_mois(mois)
    releves = ReleveCompteur.objects.filter(compteur=compteur)
    dernier = releves.filter(date__lte=fin).order_by("-date").first()
    if dernier is None or dernier.date < debut:
        return None, f"{compteur.code} : aucun relevé en {mois}."
    precedent = releves.filter(date__lt=debut).order_by("-date").first()
    if precedent is None:
        precedent = releves.filter(date__gte=debut).order_by("date").first()
        return dernier.index - precedent.index, f"{compteur.code} : pas de relevé avant {mois}, volume compté depuis le {precedent.date:%d/%m/%Y}."
    return dernier.index - precedent.index, None


def heures_machine(usine, mois):
    """Une ligne par équipement du site ayant des heures standard en vigueur ce mois."""
    debut, fin = bornes_du_mois(mois)
    fin_comptee = min(fin, timezone.localdate())
    versions = {}
    for version in CaracteristiquesEquipement.objects.filter(
        equipement__usine=usine, mois_application__lte=mois,
    ).select_related("equipement__poste__ligne", "equipement__poste__etape__sous_etape_de").order_by("equipement_id", "-mois_application"):
        versions.setdefault(version.equipement_id, version)
    exceptions = ExceptionHeures.objects.filter(date__gte=debut, date__lte=fin)
    lignes = []
    for version in versions.values():
        equipement = version.equipement
        if version.heures_marche_jour is None:
            continue
        ligne_id = equipement.poste.ligne_id if equipement.poste_id else None
        par_jour = {}
        for exception in exceptions.filter(Q(equipement=equipement) | Q(ligne_id=ligne_id) if ligne_id else Q(equipement=equipement)):
            par_jour[exception.date] = par_jour.get(exception.date, Decimal(0)) + exception.heures_en_moins
        jours_marche = JOURS_DE_LA_SEMAINE[version.jours_de_marche]
        standard, en_moins, jours = Decimal(0), Decimal(0), 0
        jour = debut
        while jour <= fin_comptee:
            if jour.weekday() in jours_marche:
                jours += 1
                standard += version.heures_marche_jour
                en_moins += min(par_jour.get(jour, Decimal(0)), version.heures_marche_jour)
            jour += timedelta(days=1)
        retenues = standard - en_moins
        bloc = bloc_de_l_equipement(equipement)
        lignes.append({
            "equipement": equipement.pk, "code": equipement.code, "designation": equipement.designation,
            "bloc": bloc.value if bloc else None, "hors_cout_eau": bloc is None,
            "jours_de_marche": jours, "heures_standard": _texte(standard, 2), "heures_en_moins": _texte(en_moins, 2),
            "heures_retenues": _texte(retenues, 2),
            "puissance_kw": _texte(version.puissance_kw), "kw_heures": _texte(retenues * version.puissance_kw, 3) if version.puissance_kw else None,
            "_exact": {"heures": retenues, "kw_heures": retenues * version.puissance_kw if version.puissance_kw else None},
        })
    return sorted(lignes, key=lambda ligne: ligne["code"])


def synthese_mois(usine, mois):
    verifier_format_mois(mois, "mois")
    debut, fin = bornes_du_mois(mois)
    alertes = []

    compteurs, site_eau, autres_sites, forage_total = [], Decimal(0), Decimal(0), None
    debitmetre_manquant = False
    for compteur in Compteur.objects.filter(usine=usine, actif=True).select_related("site_desservi"):
        volume, alerte = volume_compteur(compteur, mois)
        if alerte:
            alertes.append(alerte)
        compteurs.append({
            "compteur": compteur.pk, "code": compteur.code, "libelle": compteur.libelle, "type": compteur.type_compteur,
            "site_desservi": compteur.site_desservi.code if compteur.site_desservi_id else None, "volume_m3": _texte(volume),
        })
        if compteur.type_compteur == TypeCompteur.COMPTEUR_FORAGE:
            forage_total = (forage_total or Decimal(0)) + (volume or 0)
        elif volume is None:
            debitmetre_manquant = True
        elif compteur.site_desservi_id == usine.pk:
            site_eau += volume
        else:
            autres_sites += volume
    total_debitmetres = site_eau + autres_sites
    part = None
    if debitmetre_manquant:
        alertes.append("Un débitmètre n'est pas relevé : la part du site eau dans le forage ne peut pas être calculée.")
    elif total_debitmetres:
        part = site_eau / total_debitmetres

    heures = heures_machine(usine, mois)
    total_kwh = sum((ligne["_exact"]["kw_heures"] or 0 for ligne in heures), Decimal(0))

    pertes = PerteEau.objects.filter(usine=usine, date__gte=debut, date__lte=fin).select_related("article")
    pertes_par_type = {TypePerte.NORMALE: Decimal(0), TypePerte.ANORMALE: Decimal(0)}
    for perte in pertes:
        pertes_par_type[perte.type_perte] += perte.volume_m3 or 0

    return {
        "usine": usine.code, "mois": mois, "jusqu_au": str(min(fin, timezone.localdate())),
        "compteurs": compteurs,
        "partage_forage": {
            "volume_site_eau_m3": _texte(site_eau), "volume_autres_sites_m3": _texte(autres_sites),
            "part_site_eau": _texte(part, 6),
            "compteur_forage_m3": _texte(forage_total),
            "ecart_compteur_debitmetres_m3": _texte(forage_total - total_debitmetres) if forage_total is not None and not debitmetre_manquant else None,
        },
        "heures_machine": [{cle: valeur for cle, valeur in ligne.items() if cle != "_exact"} for ligne in heures],
        "total_kw_heures": _texte(total_kwh),
        "pertes": {
            "normales_m3": _texte(pertes_par_type[TypePerte.NORMALE]), "anormales_m3": _texte(pertes_par_type[TypePerte.ANORMALE]),
            "declarations": pertes.count(),
        },
        "alertes": alertes,
    }
