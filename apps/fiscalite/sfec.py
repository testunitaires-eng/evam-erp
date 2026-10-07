"""
Préparation de la facture normalisée (SFEC), Q67 : « prévoir dès la
conception les données et l'architecture nécessaires pour une connexion
SFEC ultérieure ».

- donnees_facture(facture) : les données à transmettre (vendeur, client,
  articles, prix TTC, taxes par groupe), déjà construites à partir de ce
  que le logiciel enregistre ;
- certifier(facture) : point d'entrée unique ; tant que la SFEC n'est pas
  activée (ParametreEntreprise.sfec_actif), il refuse clairement ;
- enregistrer_certification(...) : stocke le code, le QR code, les
  compteurs et le NIM renvoyés, imprimés ensuite sur la facture PDF.

Le connecteur réel (adresse, jeton SFEC_JETON, format exact) se branche
dans `_envoyer` quand l'administration fiscale aura ouvert l'accès.
"""

import os
from decimal import Decimal

from django.utils import timezone


def groupe_taxe(ligne):
    """Groupe de taxation : exonéré (TVA 0) ou taxable, avec le taux appliqué."""
    return "EXONERE" if not ligne.taux_tva_applique else "TAXABLE"


def donnees_facture(facture):
    from apps.core.models import ParametreEntreprise
    entreprise = ParametreEntreprise.courant()
    client = facture.client
    return {
        "type": "FV",   # facture de vente ; FA pour un avoir
        "reference": facture.numero,
        "date": timezone.localtime(facture.date_emission).isoformat() if facture.date_emission else None,
        "vendeur": {"ifu": entreprise.ifu, "raison_sociale": entreprise.raison_sociale, "nim": entreprise.sfec_nim},
        "client": {"ifu": client.ifu, "nom": client.nom, "adresse": client.adresse, "contact": client.telephone},
        "operateur": facture.commande.cree_par.username if facture.commande_id else "",
        "articles": [
            {
                "code": ligne.article.code, "designation": ligne.article.designation,
                "quantite": str(ligne.quantite), "prix_unitaire_ttc": str((Decimal(ligne.montant_ttc) / Decimal(ligne.quantite)).quantize(Decimal("0.01"))),
                "montant_ht": str(ligne.montant_ht), "groupe_taxe": groupe_taxe(ligne),
                "taux_tva": str(ligne.taux_tva_applique), "tva": str(ligne.montant_tva),
                "taxe_specifique": str(ligne.montant_accise + ligne.montant_centimes),
                "montant_ttc": str(ligne.montant_ttc),
            }
            for ligne in facture.lignes_facture.select_related("article")
        ],
        "totaux": {"ht": str(facture.montant_ht_total), "taxes": str(facture.montant_taxes_total), "ttc": str(facture.montant_total)},
        "paiement": [{"mode": e.mode_paiement, "montant": str(e.montant)} for e in facture.encaissements.all()],
    }


def certifier(facture):
    from apps.core.models import ParametreEntreprise
    entreprise = ParametreEntreprise.courant()
    if not entreprise.sfec_actif:
        raise ValueError("La certification SFEC n'est pas encore activée (paramètres de l'entreprise).")
    if facture.statut == "ANNULEE":
        raise ValueError("Une facture annulée ne se certifie pas.")
    if facture.sfec_statut == "CERTIFIEE":
        raise ValueError(f"La facture {facture.numero} est déjà certifiée.")
    if not facture.lignes_facture.exists():
        raise ValueError("La facture n'a pas encore de lignes.")
    try:
        reponse = _envoyer(entreprise, donnees_facture(facture))
    except Exception as erreur:   # erreur réseau ou refus : tracée, la facture reste non certifiée
        facture.sfec_statut, facture.sfec_message = "ERREUR", str(erreur)[:2000]
        facture.save(update_fields=["sfec_statut", "sfec_message"])
        raise ValueError(f"Certification SFEC impossible : {erreur}")
    return enregistrer_certification(facture, **reponse)


def enregistrer_certification(facture, code, qr="", compteurs="", nim="", message=""):
    facture.sfec_statut, facture.sfec_code, facture.sfec_qr = "CERTIFIEE", code, qr
    facture.sfec_compteurs, facture.sfec_nim, facture.sfec_message = compteurs, nim, message
    facture.sfec_date = timezone.now()
    facture.save(update_fields=["sfec_statut", "sfec_code", "sfec_qr", "sfec_compteurs", "sfec_nim", "sfec_date", "sfec_message"])
    return facture


def _envoyer(entreprise, donnees):
    """Connecteur à brancher : POST des données vers entreprise.sfec_url avec le jeton SFEC_JETON."""
    if not entreprise.sfec_url or not os.environ.get("SFEC_JETON"):
        raise RuntimeError("adresse du service SFEC ou jeton SFEC_JETON non configuré")
    raise RuntimeError("le connecteur SFEC n'est pas encore branché (format d'échange à recevoir de l'administration)")
