"""
Génération automatique des écritures comptables (règle §15 : une
information saisie une fois n'est jamais ressaisie, y compris en
comptabilité). Chaque fonction est appelée par le document métier, DANS
sa transaction : si l'écriture ne peut pas être passée (déséquilibre,
période clôturée), le document n'est pas enregistré non plus.

Schémas (comptes paramétrables, voir CompteParametre) :
- Facture émise      : D 411 Client (TTC) / C 70x Ventes (HT), C TVA, C accises, C centimes
- Facture annulée    : contre-passation de l'écriture de vente
- Encaissement       : D 571 Caisse | 521 Banque | Mobile Money / C 411 Client
- Décaissement       : D 658 Charges diverses (ou 411 Client si remboursement) / C 571 Caisse
- Avoir utilisé      : D 709 Rabais accordés / C 411 Client
- Réception d'achat  : D 602 Achats de matières / C 401 Fournisseur
"""

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.models import generer_numero
from .models import CleCompte, CompteParametre, EcritureComptable, Journal, LigneEcriture

CENTIME = Decimal("0.01")


def compte(cle):
    return CompteParametre.numero_de(cle)


def verifier_periode_ouverte(date):
    from .models import Cloture
    if Cloture.objects.filter(periode__in=[date.strftime("%Y-%m"), date.strftime("%Y")]).exists():
        raise ValidationError(
            f"La période comptable {date:%m/%Y} est clôturée : aucune écriture ne peut plus y être passée."
        )


def passer_ecriture(document, journal, piece, libelle, lignes, date=None):
    """
    lignes : [(compte, compte_tiers, libellé, débit, crédit), ...]
    Refuse toute écriture vide ou déséquilibrée.
    """
    date = date or timezone.localdate()
    verifier_periode_ouverte(date)
    lignes = [
        (numero, tiers, texte, Decimal(debit).quantize(CENTIME), Decimal(credit).quantize(CENTIME))
        for numero, tiers, texte, debit, credit in lignes
        if debit or credit
    ]
    total_debit = sum((ligne[3] for ligne in lignes), Decimal("0"))
    total_credit = sum((ligne[4] for ligne in lignes), Decimal("0"))
    if not lignes or total_debit != total_credit:
        raise ValidationError(
            f"Écriture comptable déséquilibrée pour {piece} (débit {total_debit}, crédit {total_credit}) : opération annulée."
        )
    ecriture = EcritureComptable.objects.create(
        numero=generer_numero("ECR"), journal=journal, date=date, piece=piece, libelle=libelle[:255],
        content_type=ContentType.objects.get_for_model(type(document)), objet_id=document.pk,
    )
    LigneEcriture.objects.bulk_create([
        LigneEcriture(ecriture=ecriture, compte=numero, compte_tiers=tiers, libelle=texte[:255], debit=debit, credit=credit)
        for numero, tiers, texte, debit, credit in lignes
    ])
    return ecriture


def ecritures_de(document):
    return EcritureComptable.objects.filter(
        content_type=ContentType.objects.get_for_model(type(document)), objet_id=document.pk,
    )


def ecrire_facture(facture):
    """Vente : le client doit le TTC ; ventes HT par compte de vente de l'article, taxes à l'État."""
    client = facture.client
    credits = {}
    taxes = {CleCompte.TVA_COLLECTEE: Decimal("0"), CleCompte.ACCISES: Decimal("0"), CleCompte.CENTIMES_ADDITIONNELS: Decimal("0")}
    for ligne in facture.lignes_facture.select_related("article"):
        numero = ligne.article.compte_vente or compte(CleCompte.VENTES_PRODUITS_FINIS)
        credits[numero] = credits.get(numero, Decimal("0")) + Decimal(ligne.montant_ht)
        taxes[CleCompte.TVA_COLLECTEE] += Decimal(ligne.montant_tva)
        taxes[CleCompte.ACCISES] += Decimal(ligne.montant_accise)
        taxes[CleCompte.CENTIMES_ADDITIONNELS] += Decimal(ligne.montant_centimes)
    libelle = f"Facture {facture.numero} - {client.nom}"
    lignes = [(numero, "", libelle, 0, montant) for numero, montant in credits.items()]
    lignes += [(compte(cle), "", f"{CleCompte(cle).label} - {facture.numero}", 0, montant) for cle, montant in taxes.items()]
    # Écart d'arrondi éventuel (TTC arrondi ligne par ligne) : sur la 1re ligne de vente.
    total_credit = sum((Decimal(l[4]).quantize(CENTIME) for l in lignes), Decimal("0"))
    ecart = Decimal(facture.montant_total).quantize(CENTIME) - total_credit
    if ecart and lignes:
        numero, tiers, texte, debit, credit = lignes[0]
        lignes[0] = (numero, tiers, texte, debit, Decimal(credit) + ecart)
    lignes.insert(0, (compte(CleCompte.CLIENTS), client.code, libelle, facture.montant_total, 0))
    return passer_ecriture(facture, Journal.VENTES, facture.numero, libelle, lignes)


def contre_passer(document, motif):
    """Annulation d'un document : écriture inverse de chacune de ses écritures."""
    for ecriture in list(ecritures_de(document)):
        lignes = [
            (l.compte, l.compte_tiers, f"{motif} - {l.libelle}", l.credit, l.debit)
            for l in ecriture.lignes.all()
        ]
        passer_ecriture(document, ecriture.journal, ecriture.piece, f"{motif} - {ecriture.libelle}", lignes)


TRESORERIE_PAR_MODE = {
    "ESPECES": CleCompte.CAISSE,
    "MOBILE_MONEY": CleCompte.MOBILE_MONEY,
    "VIREMENT": CleCompte.BANQUE,
    "CHEQUE": CleCompte.BANQUE,
}


def ecrire_encaissement(encaissement):
    facture = encaissement.facture
    libelle = f"Encaissement {encaissement.numero} - facture {facture.numero} - {facture.client.nom}"
    return passer_ecriture(encaissement, Journal.CAISSE, encaissement.numero, libelle, [
        (compte(TRESORERIE_PAR_MODE[encaissement.mode_paiement]), "", libelle, encaissement.montant, 0),
        (compte(CleCompte.CLIENTS), facture.client.code, libelle, 0, encaissement.montant),
    ])


def ecrire_decaissement(decaissement):
    """Sortie d'argent en espèces ; un remboursement de réclamation solde le compte du client."""
    from apps.reclamations.models import SolutionClient
    solution = SolutionClient.objects.filter(reference_sortie_caisse=decaissement.numero).select_related(
        "reclamation__client",
    ).first()
    if solution:
        debit = (compte(CleCompte.CLIENTS), solution.reclamation.client.code)
    else:
        debit = (compte(CleCompte.CHARGES_DIVERSES), "")
    libelle = f"Décaissement {decaissement.numero} - {decaissement.motif}"
    return passer_ecriture(decaissement, Journal.CAISSE, decaissement.numero, libelle, [
        (debit[0], debit[1], libelle, decaissement.montant, 0),
        (compte(CleCompte.CAISSE), "", libelle, 0, decaissement.montant),
    ])


def ecrire_avoir_utilise(avoir):
    libelle = f"Avoir {avoir.numero} sur facture {avoir.facture_utilisation.numero} - {avoir.client.nom}"
    return passer_ecriture(avoir, Journal.OPERATIONS_DIVERSES, avoir.numero, libelle, [
        (compte(CleCompte.RABAIS_ACCORDES), "", libelle, avoir.montant, 0),
        (compte(CleCompte.CLIENTS), avoir.client.code, libelle, 0, avoir.montant),
    ])


def ecrire_reception(ligne_reception):
    ligne_commande = ligne_reception.ligne_commande
    commande = ligne_commande.commande
    montant = Decimal(ligne_reception.quantite_recue) * Decimal(ligne_commande.prix_unitaire)
    libelle = (
        f"Réception {commande.numero} - {ligne_commande.article.code} x {ligne_reception.quantite_recue} "
        f"- {commande.fournisseur.nom}"
    )
    return passer_ecriture(ligne_reception, Journal.ACHATS, commande.numero, libelle, [
        (compte(CleCompte.ACHATS_MATIERES), "", libelle, montant, 0),
        (compte(CleCompte.FOURNISSEURS), commande.fournisseur.code, libelle, 0, montant),
    ])
