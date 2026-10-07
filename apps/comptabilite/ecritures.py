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
- Réception d'achat  : D 60x Achats (selon la nature de l'article) / C 401 Fournisseur
- Ventes comptoir    : particuliers au comptant -> pas d'écriture par facture ni par
                       encaissement, mais une SYNTHÈSE à la clôture de la session de
                       caisse : D 571 (ou banque / Mobile Money) / C 702x, C taxes
Les comptes de vente (702x par activité, format...) et d'achat (par nature
d'article) se paramètrent dans RegleCompte.
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


def compte_de_vente(article):
    """Compte de vente : compte saisi sur l'article, sinon règle paramétrée (702x par activité / format), sinon défaut."""
    from .models import RegleCompte, SensCompte
    return (article.compte_vente or RegleCompte.compte_pour(article, SensCompte.VENTE)
            or compte(CleCompte.VENTES_PRODUITS_FINIS))


def compte_d_achat(article):
    """Compte d'achat selon la nature de l'article (règle paramétrée), sinon achats de matières."""
    from .models import RegleCompte, SensCompte
    return RegleCompte.compte_pour(article, SensCompte.ACHAT) or compte(CleCompte.ACHATS_MATIERES)


def credits_de_vente(facture, part=Decimal(1)):
    """{compte: montant} des ventes HT (par compte de vente) et des taxes d'une facture, au prorata `part`."""
    credits = {}
    for ligne in facture.lignes_facture.select_related("article"):
        for numero, montant in (
            (compte_de_vente(ligne.article), ligne.montant_ht), (compte(CleCompte.TVA_COLLECTEE), ligne.montant_tva),
            (compte(CleCompte.ACCISES), ligne.montant_accise), (compte(CleCompte.CENTIMES_ADDITIONNELS), ligne.montant_centimes),
        ):
            if montant:
                credits[numero] = credits.get(numero, Decimal("0")) + Decimal(montant) * part
    return credits


def equilibrer(lignes, total):
    """Arrondi : l'écart au centime va sur la plus grosse ligne de crédit."""
    lignes = [(n, t, x, d, Decimal(c).quantize(CENTIME)) for n, t, x, d, c in lignes]
    ecart = Decimal(total).quantize(CENTIME) - sum((l[4] for l in lignes), Decimal("0"))
    if ecart and lignes:
        index = max(range(len(lignes)), key=lambda i: lignes[i][4])
        numero, tiers, texte, debit, credit = lignes[index]
        lignes[index] = (numero, tiers, texte, debit, credit + ecart)
    return lignes


def vente_en_synthese(facture):
    """
    Q63 : vente au comptant à un particulier en caisse -> pas de compte
    client individuel ; elle est comptabilisée dans l'écriture de synthèse
    de la session de caisse (D 571 / C 702x, taxes), le détail restant
    dans la caisse.
    """
    return facture.client.type_client == "PARTICULIER" and facture.commande.type_commande == "COMPTANT"


def ecrire_facture(facture):
    """Vente : le client doit le TTC ; ventes HT par compte de vente (702x), taxes à l'État."""
    if vente_en_synthese(facture):
        return None
    client = facture.client
    libelle = f"Facture {facture.numero} - {client.nom}"
    lignes = [(numero, "", libelle, 0, montant) for numero, montant in credits_de_vente(facture).items()]
    lignes = equilibrer(lignes, facture.montant_total)
    lignes.insert(0, (compte(CleCompte.CLIENTS), client.code, libelle, facture.montant_total, 0))
    return passer_ecriture(facture, Journal.VENTES, facture.numero, libelle, lignes)


def ecrire_synthese_caisse(session):
    """
    Clôture de session : une écriture de synthèse pour les ventes au
    comptant aux particuliers encaissées dans la session :
    D 571 / 521 / 5215 (par mode de paiement) / C 702x (HT par compte de
    vente) et C taxes, au prorata de chaque encaissement.
    """
    debits, credits, total = {}, {}, Decimal("0")
    for encaissement in session.encaissements.select_related("facture__client", "facture__commande"):
        facture = encaissement.facture
        if not vente_en_synthese(facture) or not facture.montant_total:
            continue
        part = Decimal(encaissement.montant) / Decimal(facture.montant_total)
        tresorerie = compte(TRESORERIE_PAR_MODE[encaissement.mode_paiement])
        debits[tresorerie] = debits.get(tresorerie, Decimal("0")) + Decimal(encaissement.montant)
        for numero, montant in credits_de_vente(facture, part).items():
            credits[numero] = credits.get(numero, Decimal("0")) + montant
        total += Decimal(encaissement.montant)
    if not total:
        return None
    libelle = f"Synthèse ventes comptoir - {session.caisse.nom} - session {session.pk} du {session.date_cloture:%d/%m/%Y}"
    lignes = [(numero, "", libelle, montant, 0) for numero, montant in debits.items()]
    lignes += equilibrer([(numero, "", libelle, 0, montant) for numero, montant in credits.items()], total)
    return passer_ecriture(session, Journal.CAISSE, f"CAISSE-{session.pk}", libelle, lignes)


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
    if vente_en_synthese(facture):
        return None   # comptabilisé dans la synthèse de la session de caisse
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
        (compte_d_achat(ligne_commande.article), "", libelle, montant, 0),
        (compte(CleCompte.FOURNISSEURS), commande.fournisseur.code, libelle, 0, montant),
    ])
