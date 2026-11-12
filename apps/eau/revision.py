"""
Révision du coût standard après la clôture d'un mois (onglets « Révision
du standard » et « Scénario 3 mois », partie E ; règle 17).

    Écart hors charges au besoin = coût réel au m³ hors charges au besoin
        et exceptionnelles ÷ standard en vigueur - 1 (une panne isolée ne
        change pas le standard).
    - volume du mois < seuil de volume minimal x volume prévu :
      standard maintenu (volume trop faible pour être représentatif) ;
    - |écart| <= seuil d'écart : standard maintenu ;
    - au-delà : le coût réel hors charges au besoin est proposé comme
      standard du mois suivant, à valider par le contrôle de gestion.
Pas de blocage au démarrage : la règle s'applique dès le premier mois.
"""

from decimal import Decimal

from .calculs import CENTIME, calcul_previsionnel
from .models import (
    ClotureMoisEau, CoutStandardEau, DecisionRevision, OrigineStandard, ParametresEau, ajouter_mois,
)

SEUIL_ECART_DEFAUT = Decimal(5)
SEUIL_VOLUME_DEFAUT = Decimal(50)


def reviser(cloture, calcul, utilisateur=None):
    """Décide (et enregistre sur la clôture) le maintien du standard ou la proposition d'un nouveau."""
    from apps.comptes.models import Profil
    from apps.core.notifications import notifier
    usine, mois, exact = cloture.usine, cloture.mois, calcul["_exact"]
    parametres = ParametresEau.en_vigueur(mois, usine=usine)
    seuil_ecart = parametres.seuil_ecart_standard_pct if parametres else SEUIL_ECART_DEFAUT
    seuil_volume = parametres.seuil_volume_minimal_pct if parametres else SEUIL_VOLUME_DEFAUT
    volume_prevu = calcul_previsionnel(usine, mois)["_exact"]["volume"] or None
    ecart = exact["cout_m3_courant"] / exact["standard_m3"] - 1
    ecart_pct = ecart * 100
    au_dela = abs(ecart_pct) > seuil_ecart
    propose = None
    if volume_prevu is not None and exact["volume"] < volume_prevu * seuil_volume / 100:
        decision = DecisionRevision.MAINTENU_VOLUME_FAIBLE
    elif au_dela:
        decision = DecisionRevision.NOUVEAU_PROPOSE
        synthese = calcul["synthese"]
        propose = CoutStandardEau.objects.create(
            usine=usine, mois_application=ajouter_mois(mois, 1), origine=OrigineStandard.REVISION,
            volume_m3=exact["volume"].quantize(Decimal("0.001")),
            cout_forage=Decimal(synthese["cout_forage_site_eau"]), cout_traitement=Decimal(synthese["cout_traitement"]),
            cout_mensuel=exact["cout_courant"].quantize(CENTIME), cout_m3=exact["cout_m3_courant"].quantize(Decimal("0.0001")),
            detail={"revision_du_mois": mois, "ecart_courant_pct": format(ecart_pct.quantize(Decimal("0.01")), "f"),
                    "synthese": synthese},
            propose_par=utilisateur,
            motif=f"Révision après la clôture de {mois} : écart hors charges au besoin de {ecart_pct.quantize(Decimal('0.01'))} %.",
        )
    else:
        decision = DecisionRevision.MAINTENU
    ClotureMoisEau.objects.filter(pk=cloture.pk).update(
        decision=decision, ecart_courant_pct=ecart_pct.quantize(Decimal("0.0001")),
        volume_prevu_m3=volume_prevu.quantize(Decimal("0.001")) if volume_prevu is not None else None,
        standard_propose=propose,
    )
    cloture.refresh_from_db()

    destinataires = [Profil.CONTROLE_GESTION]
    if au_dela:
        suite = {
            DecisionRevision.NOUVEAU_PROPOSE: f"nouveau standard proposé pour {ajouter_mois(mois, 1)} : "
                                              f"{propose.cout_m3.quantize(CENTIME) if propose else ''} FCFA/m³, à valider.",
            DecisionRevision.MAINTENU_VOLUME_FAIBLE: "standard maintenu : volume du mois trop faible.",
        }[decision]
        notifier(
            f"Écart de coût de l'eau au-delà du seuil : {mois}",
            f"{usine.code} - écart hors charges au besoin {ecart_pct.quantize(Decimal('0.01'))} % (seuil {seuil_ecart} %) ; {suite}",
            document=propose, profils=destinataires,
        )
    if Decimal(calcul["volumes"]["pertes_rejets_anormales_m3"] or 0) > 0:
        notifier(
            f"Pertes anormales d'eau : {mois}",
            f"{usine.code} - taux de rejet au-delà du seuil toléré : {calcul['volumes']['pertes_rejets_anormales_m3']} m³ "
            f"(valeur {calcul['synthese']['valeur_perte_anormale']} FCFA), suivis hors coût standard.",
            profils=destinataires,
        )
    return cloture


def evolution(usine, depuis=None, jusqu_a=None):
    """Courbe mois par mois : coût réel au m³, réel hors charges au besoin, standard, écarts, décision."""
    clotures = ClotureMoisEau.objects.filter(usine=usine).select_related("standard_propose").order_by("mois")
    if depuis:
        clotures = clotures.filter(mois__gte=depuis)
    if jusqu_a:
        clotures = clotures.filter(mois__lte=jusqu_a)
    lignes = []
    for cloture in clotures:
        standard = cloture.cout_standard_m3
        ecart_total = (cloture.cout_m3 / standard - 1) * 100 if standard else None
        propose = cloture.standard_propose
        lignes.append({
            "mois": cloture.mois, "volume_m3": format(cloture.volume_m3.normalize(), "f"),
            "cout_m3": str(cloture.cout_m3.quantize(CENTIME)), "cout_m3_courant": str(cloture.cout_m3_courant.quantize(CENTIME)),
            "cout_standard_m3": str(standard.quantize(CENTIME)),
            "ecart_total_pct": str(ecart_total.quantize(Decimal("0.01"))) if ecart_total is not None else None,
            "ecart_courant_pct": str(cloture.ecart_courant_pct.quantize(Decimal("0.01"))) if cloture.ecart_courant_pct is not None else None,
            "decision": cloture.decision, "decision_libelle": cloture.get_decision_display() if cloture.decision else "",
            "standard_propose": None if propose is None else {
                "id": propose.pk, "mois_application": propose.mois_application,
                "cout_m3": str(propose.cout_m3.quantize(CENTIME)), "statut": propose.statut,
            },
        })
    return {"usine": usine.code, "mois": lignes}
