"""
Les documents imprimables d'EVAM, construits avec apps/core/pdf.py.
Chaque fonction reçoit l'objet (déjà autorisé par la vue) et l'utilisateur
qui imprime, et retourne un DocumentPDF.
"""

from decimal import Decimal

from .pdf import DocumentPDF, date_fr, montant, nombre


def _quantite(valeur, unite=""):
    return f"{nombre(valeur)} {unite}".strip()


def _unite(article):
    return article.get_unite_mesure_display() if hasattr(article, "get_unite_mesure_display") else ""


def facture(facture, utilisateur=None):
    """Facture client : lignes avec taxes appliquées (TVA, accise, centimes), totaux, montant en lettres."""
    client = facture.client
    commande = facture.commande
    document = DocumentPDF(
        "FACTURE", facture.numero, facture.date_emission, utilisateur,
        filigrane="ANNULÉE" if facture.statut == "ANNULEE" else None,
    )
    document.avec_tiers(
        "Client", [client.nom, client.adresse, client.telephone and f"Tél. {client.telephone}",
                   client.ifu and f"IFU {client.ifu}", f"Code client : {client.code}"],
        "Références", [
            f"Commande : {commande.numero} du {date_fr(commande.date_commande)}",
            f"Vente : {commande.get_type_commande_display()}",
            f"Échéance : {date_fr(facture.date_echeance)}" if facture.date_echeance else "Payable à la commande",
            f"Statut : {facture.get_statut_display()}",
        ],
    )
    lignes, totaux_taxes = [], {"accise": Decimal(0), "tva": Decimal(0), "centimes": Decimal(0)}
    for ligne in facture.lignes_facture.select_related("article"):
        lignes.append([
            ligne.article.code, ligne.article.designation, nombre(ligne.quantite), montant(ligne.prix_unitaire_ht),
            f"{nombre(ligne.taux_tva_applique)} %", montant(ligne.montant_ht), montant(ligne.montant_ttc),
        ])
        totaux_taxes["accise"] += ligne.montant_accise
        totaux_taxes["tva"] += ligne.montant_tva
        totaux_taxes["centimes"] += ligne.montant_centimes
    document.avec_lignes(
        ["Code", "Désignation", "Qté", "P.U. HT", "TVA", "Montant HT", "Montant TTC"], lignes,
        [27, None, 16, 24, 14, 26, 26], colonnes_nombres=(2, 3, 4, 5, 6),
    )
    totaux = [("Total HT", montant(facture.montant_ht_total))]
    if totaux_taxes["accise"]:
        totaux.append(("Droits d'accise", montant(totaux_taxes["accise"])))
    if totaux_taxes["centimes"]:
        totaux.append(("Centimes additionnels", montant(totaux_taxes["centimes"])))
    totaux.append(("TVA", montant(totaux_taxes["tva"])))
    paye = facture.montant_paye
    if paye:
        totaux.append(("Total TTC", montant(facture.montant_total)))
        totaux.append(("Déjà réglé", montant(paye)))
        totaux.append(("Reste à payer (FCFA)", montant(facture.solde_restant)))
    else:
        totaux.append(("Net à payer TTC (FCFA)", montant(facture.montant_total)))
    document.avec_totaux(totaux, en_lettres_de=facture.montant_total, libelle_lettres="Arrêtée la présente facture à la somme de")
    document.avec_texte(document.entreprise.conditions_paiement)
    return document.avec_signatures("Le client", f"Pour {document.entreprise.raison_sociale}")


def avoir(avoir, utilisateur=None):
    client = avoir.client
    document = DocumentPDF("AVOIR", avoir.numero, avoir.date_creation, utilisateur,
                           filigrane="ANNULÉ" if avoir.statut == "ANNULE" else None)
    document.avec_tiers(
        "Client", [client.nom, client.adresse, client.ifu and f"IFU {client.ifu}", f"Code client : {client.code}"],
        "Références", [
            f"Facture d'origine : {avoir.facture_origine.numero}" if avoir.facture_origine_id else "",
            f"Statut : {avoir.get_statut_display()}",
            f"Utilisé sur : {avoir.facture_utilisation.numero}" if avoir.facture_utilisation_id else "",
        ],
    )
    document.avec_lignes(["Motif", "Montant"], [[avoir.motif, montant(avoir.montant)]], [None, 36], colonnes_nombres=(1,))
    document.avec_totaux([("Montant de l'avoir (FCFA)", montant(avoir.montant))], en_lettres_de=avoir.montant,
                         libelle_lettres="Arrêté le présent avoir à la somme de")
    return document.avec_signatures("Le client", f"Pour {document.entreprise.raison_sociale}")


def bon_livraison(bon, utilisateur=None):
    """Bon de livraison : quantités livrées, sans prix, signatures chauffeur / client."""
    commande = bon.commande
    client = commande.client
    preparation = getattr(commande, "preparation", None)
    tournee = bon.tournee
    document = DocumentPDF("BON DE LIVRAISON", bon.numero, bon.date_generation, utilisateur)
    document.avec_tiers(
        "Livré à", [client.nom, client.adresse, client.telephone and f"Tél. {client.telephone}"],
        "Références", [
            f"Commande : {commande.numero}",
            f"Facture : {commande.facture.numero}" if getattr(commande, "facture", None) else "",
            f"Expédié depuis : {preparation.depot.nom}" if preparation and preparation.depot_id else "",
            f"Tournée : {tournee.numero} - {tournee.vehicule.immatriculation}" if tournee else "",
            f"Chauffeur : {tournee.chauffeur}" if tournee else "",
            f"Statut : {bon.get_statut_display()}",
        ],
    )
    lignes = [
        [l.article.code, l.article.designation, _quantite(l.quantite), l.article.unite_vente.nom if l.article.unite_vente_id else _unite(l.article)]
        for l in commande.lignes.select_related("article", "article__unite_vente")
    ]
    document.avec_lignes(["Code", "Désignation", "Quantité", "Unité"], lignes, [27, None, 26, 34], colonnes_nombres=(2,))
    document.avec_texte("Marchandise reçue en bon état et conforme à la commande, sauf réserves écrites ci-dessous.")
    if bon.incident_livraison:
        document.avec_texte(f"Réserves / incident : {bon.incident_livraison}")
    return document.avec_signatures("Le magasinier", "Le chauffeur", "Le client (nom, date, signature)")


def commande_fournisseur(commande, utilisateur=None):
    fournisseur = commande.fournisseur
    document = DocumentPDF("BON DE COMMANDE", commande.numero, commande.date_commande, utilisateur,
                           filigrane={"BROUILLON": "BROUILLON", "ANNULEE": "ANNULÉE"}.get(commande.statut))
    document.avec_tiers(
        "Fournisseur", [fournisseur.nom, fournisseur.adresse, fournisseur.telephone and f"Tél. {fournisseur.telephone}",
                        fournisseur.email, fournisseur.ifu and f"IFU {fournisseur.ifu}", f"Code fournisseur : {fournisseur.code}"],
        "Livraison", [
            document.entreprise.raison_sociale, document.entreprise.adresse, document.entreprise.ville,
            f"Statut : {commande.get_statut_display()}",
        ],
    )
    total, lignes = Decimal(0), []
    for ligne in commande.lignes.select_related("article"):
        montant_ligne = ligne.quantite_commandee * ligne.prix_unitaire
        total += montant_ligne
        lignes.append([ligne.article.code, ligne.article.designation, _quantite(ligne.quantite_commandee),
                       _unite(ligne.article), montant(ligne.prix_unitaire), montant(montant_ligne)])
    document.avec_lignes(["Code", "Désignation", "Quantité", "Unité", "Prix unitaire", "Montant"], lignes,
                         [27, None, 22, 22, 26, 28], colonnes_nombres=(2, 4, 5))
    document.avec_totaux([("Total de la commande (FCFA)", montant(total))], en_lettres_de=total,
                         libelle_lettres="Arrêté le présent bon de commande à la somme de")
    document.avec_texte("Merci de rappeler le numéro de ce bon de commande sur votre bon de livraison et votre facture, "
                        "et d'indiquer le numéro de lot et la date limite de chaque produit livré.")
    return document.avec_signatures("Le responsable des achats", "La direction")


def recu_caisse(encaissement, utilisateur=None):
    facture = encaissement.facture
    session = encaissement.session_caisse
    caissier = encaissement.encaisse_par or session.caissier
    document = DocumentPDF("REÇU DE CAISSE", encaissement.numero, encaissement.date_encaissement, utilisateur)
    document.avec_tiers(
        "Reçu de", [facture.client.nom, facture.client.telephone and f"Tél. {facture.client.telephone}",
                    f"Code client : {facture.client.code}"],
        "Caisse", [session.caisse.nom, f"Caissier : {caissier.get_full_name() or caissier.username}",
                   f"Mode de paiement : {encaissement.get_mode_paiement_display()}"],
    )
    document.avec_lignes(
        ["Facture", "Montant TTC", "Déjà réglé avant", "Montant reçu", "Reste à payer"],
        [[facture.numero, montant(facture.montant_total), montant(facture.montant_paye - encaissement.montant),
          montant(encaissement.montant), montant(facture.solde_restant)]],
        [None, 30, 32, 30, 30], colonnes_nombres=(1, 2, 3, 4),
    )
    document.avec_totaux([("Montant reçu (FCFA)", montant(encaissement.montant))], en_lettres_de=encaissement.montant,
                         libelle_lettres="Reçu la somme de")
    return document.avec_signatures("Le client", "Le caissier")


def bon_sortie(of, utilisateur=None):
    """Bon de sortie des matières d'un OF (pour le magasin), sans aucun prix."""
    document = DocumentPDF("BON DE SORTIE MATIÈRES", of.numero, of.date_creation, utilisateur)
    document.avec_tiers(
        "Ordre de fabrication", [
            f"{of.article.code} - {of.article.designation}", f"Quantité à produire : {nombre(of.quantite_a_produire)}",
            f"Recette : version {of.fiche_technique.version}" if of.fiche_technique_id else "",
            f"Statut : {of.get_statut_display()}",
        ],
        "Magasin", [of.depot_matieres.nom, f"Ligne : {of.ligne.code} - {of.ligne.designation}" if of.ligne_id else "",
                    f"Usine : {of.usine.nom}" if of.usine else "", f"Responsable : {of.responsable.get_full_name() or of.responsable.username}"],
    )
    lignes = []
    for besoin in of.besoins_matieres.select_related("matiere"):
        sorti = sum((s.quantite_sortie for s in of.sorties_matieres.filter(matiere=besoin.matiere)), Decimal(0))
        lots = ", ".join(sorted({
            c.lot.numero for s in of.sorties_matieres.filter(matiere=besoin.matiere) for c in s.consommations_lots.select_related("lot")
        }))
        lignes.append([besoin.matiere.code, besoin.matiere.designation, _quantite(besoin.quantite_theorique, besoin.matiere.unite_mesure),
                       _quantite(sorti, besoin.matiere.unite_mesure), lots or "", ""])
    document.avec_lignes(["Code", "Matière / emballage", "À sortir", "Déjà sorti", "Lots", "Servi"], lignes,
                         [27, None, 26, 26, 34, 18], colonnes_nombres=(2, 3))
    return document.avec_signatures("Le magasinier", "Le responsable production (réception)")


def bon_transfert(transfert, utilisateur=None):
    document = DocumentPDF("BON DE TRANSFERT", transfert.numero, transfert.date_expedition or transfert.date_creation, utilisateur,
                           filigrane={"BROUILLON": "BROUILLON", "ANNULE": "ANNULÉ"}.get(transfert.statut))
    document.avec_tiers(
        "Expéditeur", [transfert.depot_source.nom, transfert.depot_source.code, transfert.depot_source.adresse,
                       f"Expédié le {date_fr(transfert.date_expedition)}" if transfert.date_expedition else ""],
        "Destinataire", [transfert.depot_destination.nom, transfert.depot_destination.code, transfert.depot_destination.adresse,
                         f"Reçu le {date_fr(transfert.date_reception)}" if transfert.date_reception else "",
                         f"Statut : {transfert.get_statut_display()}"],
    )
    lignes = [[l.article.code, l.article.designation, l.lot.numero_lot if l.lot_id else "", _quantite(l.quantite), _unite(l.article)]
              for l in transfert.lignes.select_related("article", "lot")]
    document.avec_lignes(["Code", "Désignation", "Lot", "Quantité", "Unité"], lignes, [27, None, 32, 24, 24], colonnes_nombres=(3,))
    document.avec_texte(transfert.observations)
    return document.avec_signatures("Expédié par (magasin)", "Le transporteur", "Reçu par (dépôt)")
