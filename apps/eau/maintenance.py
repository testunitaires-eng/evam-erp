"""
Échéances de maintenance du site eau (onglet « Module traitement »,
partie B - Alertes), sans aucun coût : consultables par les techniciens.

- Maintenance préventive : pour chaque opération du plan (élément de coût
  « Préventive » non retiré), intervalle = durée de la période ÷ fréquence
  (ex : 3 fois par an = tous les 122 jours ; 2 fois par mois = tous les
  15 jours). Prochaine échéance = dernière intervention préventive de
  l'opération + intervalle ; jamais faite : début du plan (1er jour du
  mois de sa première version) + intervalle. Alerte 7 jours avant, puis
  à l'échéance.
- Fin de vie : un lot étalé encore (en partie) en place, dans son
  dernier mois de durée de vie (alerte « 1 mois avant » la fin) ou au-delà.
- Charge attendue non imputée : 5 jours avant la date limite de clôture
  du mois précédent (comptabilité et contrôle de gestion).

envoyer_alertes() est appelé chaque jour par la commande `alertes_eau` ;
chaque alerte n'est envoyée qu'une fois (AlerteEnvoyee).
"""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    AlerteEnvoyee, ElementCout, Famille, Installation, Periode, TypeIntervention, VersionElementCout, mois_de,
)

JOURS_DES_PERIODES = {
    Periode.JOUR: Decimal(1),
    Periode.SEMAINE: Decimal(7),
    Periode.MOIS: Decimal(365) / 12,
    Periode.AN: Decimal(365),
}
PREAVIS_PREVENTIVE_JOURS = 7


class Statut:
    EN_RETARD = "EN_RETARD"
    A_FAIRE = "A_FAIRE"          # dans les 7 jours (ou aujourd'hui)
    A_VENIR = "A_VENIR"
    FIN_DE_VIE_PROCHE = "FIN_DE_VIE_PROCHE"   # dernier mois de la durée de vie
    FIN_DE_VIE_DEPASSEE = "FIN_DE_VIE_DEPASSEE"
    EN_SERVICE = "EN_SERVICE"


def intervalle_jours(frequence, periode):
    """Jours entre deux opérations (au moins 1)."""
    jours = (JOURS_DES_PERIODES[periode] / Decimal(frequence)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return max(int(jours), 1)


def echeances_preventives(usine, jour=None):
    jour = jour or timezone.localdate()
    mois = mois_de(jour)
    lignes = []
    operations = ElementCout.objects.filter(usine=usine, famille=Famille.PREVENTIVE).select_related("equipement", "etape")
    for operation in operations:
        version = VersionElementCout.en_vigueur(mois, element=operation)
        if version is None or version.retire or not version.frequence or not version.periode:
            continue
        intervalle = intervalle_jours(version.frequence, version.periode)
        derniere = operation.interventions.filter(
            type_intervention=TypeIntervention.PREVENTIVE, date__lte=jour,
        ).order_by("-date").first()
        if derniere is not None:
            reference = derniere.date
        else:
            premiere = operation.versions.order_by("mois_application").first()
            annee, numero = (int(x) for x in premiere.mois_application.split("-"))
            reference = date(annee, numero, 1)
        echeance = reference + timedelta(days=intervalle)
        reste = (echeance - jour).days
        statut = Statut.EN_RETARD if reste < 0 else Statut.A_FAIRE if reste <= PREAVIS_PREVENTIVE_JOURS else Statut.A_VENIR
        lignes.append({
            "operation": operation.pk, "libelle": operation.libelle, "etape": operation.etape.libelle,
            "equipement": operation.equipement.code if operation.equipement_id else None,
            "frequence": f"{format(version.frequence.normalize(), 'f')} par {Periode(version.periode).label.lower()}",
            "intervalle_jours": intervalle,
            "derniere_intervention": str(derniere.date) if derniere else None,
            "prochaine_echeance": str(echeance), "jours_restants": reste, "statut": statut,
        })
    return sorted(lignes, key=lambda ligne: (ligne["prochaine_echeance"], ligne["libelle"]))


def fins_de_vie(usine, jour=None):
    """Lots étalés encore (en partie) en place, avec leur fin de vie (sans prix)."""
    mois = mois_de(jour or timezone.localdate())
    lignes = []
    lots = Installation.objects.filter(element__usine=usine, mois_installation__lte=mois).select_related("element__equipement")
    for lot in lots:
        en_place = lot.quantite_en_place(mois)
        if en_place <= 0:
            continue
        fin = lot.dernier_mois
        statut = Statut.FIN_DE_VIE_DEPASSEE if mois > fin else Statut.FIN_DE_VIE_PROCHE if mois == fin else Statut.EN_SERVICE
        lignes.append({
            "installation": lot.pk, "element": lot.element_id, "libelle": lot.element.libelle,
            "equipement": lot.element.equipement.code if lot.element.equipement_id else None,
            "quantite_en_place": format(en_place.normalize(), "f"), "mois_installation": lot.mois_installation,
            "duree_vie_mois": lot.duree_vie_mois, "dernier_mois": fin, "statut": statut,
        })
    return sorted(lignes, key=lambda ligne: (ligne["dernier_mois"], ligne["libelle"]))


def echeances(usine, jour=None):
    jour = jour or timezone.localdate()
    return {
        "usine": usine.code, "date": str(jour),
        "preventive": echeances_preventives(usine, jour),
        "fins_de_vie": fins_de_vie(usine, jour),
    }


def _premiere_fois(cle):
    try:
        with transaction.atomic():
            AlerteEnvoyee.objects.create(cle=cle)
    except IntegrityError:
        return False
    return True


def envoyer_alertes(jour=None):
    """Notifie techniciens et contrôle de gestion des échéances du jour (une seule fois chacune). Renvoie le nombre d'alertes."""
    from apps.comptes.models import Profil
    from apps.core.notifications import notifier
    from apps.industriel.models import Usine
    jour = jour or timezone.localdate()
    destinataires = [Profil.TECHNICIEN_EAU, Profil.CONTROLE_GESTION]
    envoyees = 0
    for usine in Usine.objects.filter(elements_cout_eau__isnull=False).distinct():
        for ligne in echeances_preventives(usine, jour):
            if ligne["statut"] == Statut.A_VENIR:
                continue
            echue = ligne["jours_restants"] <= 0
            cle = f"preventive:{ligne['operation']}:{ligne['prochaine_echeance']}:{'echeance' if echue else 'preavis'}"
            if not _premiere_fois(cle):
                continue
            quand = "à faire aujourd'hui" if ligne["jours_restants"] == 0 else (
                f"en retard depuis le {date.fromisoformat(ligne['prochaine_echeance']):%d/%m/%Y}" if echue
                else f"à faire avant le {date.fromisoformat(ligne['prochaine_echeance']):%d/%m/%Y}"
            )
            notifier(f"Maintenance préventive : {ligne['libelle']}", f"{usine.code} - {quand} ({ligne['frequence']}).",
                     profils=destinataires)
            envoyees += 1
        for ligne in fins_de_vie(usine, jour):
            if ligne["statut"] == Statut.EN_SERVICE or not _premiere_fois(f"fin_de_vie:{ligne['installation']}"):
                continue
            notifier(f"Fin de vie : {ligne['libelle']}",
                     f"{usine.code} - installé(e) en {ligne['mois_installation']}, durée de vie {ligne['duree_vie_mois']} mois : "
                     f"dernier mois {ligne['dernier_mois']}. Prévoir le remplacement.",
                     profils=destinataires)
            envoyees += 1
    envoyees += _alertes_charges_attendues(jour)
    return envoyees


PREAVIS_CLOTURE_JOURS = 5


def _alertes_charges_attendues(jour):
    """5 jours avant la date limite de clôture : charges attendues ni imputées ni validées sans imputation."""
    from apps.comptes.models import Profil
    from apps.core.notifications import notifier
    from apps.industriel.models import Usine
    from .models import ClotureMoisEau
    from .reel import charges_attendues, date_limite_cloture, mois_a_cloturer
    mois = mois_a_cloturer(jour)
    envoyees = 0
    for usine in Usine.objects.filter(elements_cout_eau__attendue_chaque_mois=True).distinct():
        limite = date_limite_cloture(usine, mois)
        if jour < limite - timedelta(days=PREAVIS_CLOTURE_JOURS) or ClotureMoisEau.objects.filter(usine=usine, mois=mois).exists():
            continue
        for ligne in charges_attendues(usine, mois):
            if ligne["statut"] != "MANQUANTE" or not _premiere_fois(f"attendue:{ligne['element']}:{mois}"):
                continue
            notifier(
                f"Charge attendue non imputée : {ligne['libelle']}",
                f"{usine.code} - {mois} : à imputer ou à valider « sans imputation » (avec un motif) avant le {limite:%d/%m/%Y}.",
                profils=[Profil.COMPTABILITE_DAF, Profil.CONTROLE_GESTION],
            )
            envoyees += 1
    return envoyees
