"""
Notifications automatiques : chaque événement métier prévient les
personnes qui doivent agir ensuite (« À faire »), selon le document UX
par rôle. Deux déclencheurs :
- REGLES_STATUT : appliquées automatiquement à chaque création /
  changement de statut d'un document (voir historique.py) ;
- notifier() : appelé directement pour les événements sans statut
  (besoin d'achat automatique, affectation d'agents, anomalie...).
L'auteur de l'action n'est jamais notifié de sa propre action.
"""

from apps.comptes.models import Profil

# (app.modèle, nouveau statut) -> destinataires et texte.
# « profils » : tous les comptes actifs de ces profils ;
# « champ » : un utilisateur désigné par le document (chemin d'attributs).
REGLES_STATUT = {
    ("caisse.decaissement", "EN_ATTENTE"): {
        "profils": [Profil.DIRECTION, Profil.COMPTABILITE_DAF], "titre": "Décaissement à autoriser",
        "message": "{objet.montant} FCFA - {objet.motif}",
    },
    ("caisse.decaissement", "AUTORISE"): {"champ": "effectue_par", "titre": "Décaissement autorisé : à effectuer"},
    ("caisse.decaissement", "REFUSE"): {"champ": "effectue_par", "titre": "Décaissement refusé", "message": "{objet.motif_refus}"},
    ("production.demandematiere", "A_PREPARER"): {
        "profils": [Profil.MAGASINIER], "titre": "Matières à livrer à l'atelier",
        "message": "{objet.matiere.code} x {objet.quantite_demandee} pour {objet.ordre_fabrication.numero}",
    },
    ("production.demandecomplementaire", "EN_ATTENTE"): {
        "profils": [Profil.MAGASINIER], "titre": "Demande complémentaire à traiter",
        "message": "{objet.matiere.code} x {objet.quantite} - {objet.motif}",
    },
    ("production.demandecomplementaire", "APPROUVEE_ET_LIVREE"): {"champ": "demandeur", "titre": "Complément livré"},
    ("production.demandecomplementaire", "REJETEE"): {"champ": "demandeur", "titre": "Demande complémentaire rejetée"},
    ("achats.demandeachat", "EN_ATTENTE"): {
        "profils": [Profil.RESPONSABLE_ACHATS], "titre": "Demande d'achat à approuver",
        "message": "{objet.article.code} x {objet.quantite_demandee}",
    },
    ("achats.demandeachat", "APPROUVEE"): {"champ": "demandeur", "titre": "Demande d'achat approuvée"},
    ("achats.demandeachat", "REJETEE"): {"champ": "demandeur", "titre": "Demande d'achat rejetée"},
    ("achats.commandefournisseur", "ENVOYEE"): {
        "profils": [Profil.MAGASINIER], "titre": "Réception attendue", "message": "Fournisseur : {objet.fournisseur.nom}",
    },
    ("commercial.commande", "VALIDEE"): {
        "profils": [Profil.RESPONSABLE_DISTRIBUTION], "titre": "Commande à servir", "message": "Client : {objet.client.nom}",
    },
    ("commercial.facture", "EMISE"): {
        "profils": [Profil.CAISSIER], "titre": "Facture à encaisser", "message": "Client : {objet.client.nom}",
    },
    ("distribution.preparationlivraison", "A_PREPARER"): {
        "profils": [Profil.MAGASINIER], "titre": "Préparation à faire", "message": "Commande {objet.commande.numero}",
    },
    ("distribution.bonlivraison", "EN_LIVRAISON"): {
        "champ": "tournee.chauffeur.utilisateur", "titre": "Nouvelle livraison",
        "message": "{objet.commande.client.nom} - {objet.commande.client.adresse}",
    },
    ("qualite.lot", "EN_ATTENTE"): {
        "profils": [Profil.RESPONSABLE_QUALITE], "titre": "Lot à contrôler", "message": "{objet.article.designation} x {objet.quantite}",
    },
    ("qualite.lot", "LIBERE"): {
        "profils": [Profil.COMMERCIAL, Profil.RESPONSABLE_PRODUCTION], "titre": "Lot libéré : disponible à la vente",
        "message": "{objet.article.designation} x {objet.quantite}",
    },
    ("referentiel.fichetechnique", "BROUILLON"): {
        "profils": [Profil.ADMIN_SI], "titre": "Fiche de composition à paramétrer",
        "message": "{objet.article.code} - {objet.article.designation} (v{objet.version})",
    },
    ("production.ordrefabrication", "EN_PRODUCTION"): {
        "champ": "agents_affectes", "titre": "OF démarré : saisie de production ouverte",
        "message": "{objet.article.designation} x {objet.quantite_a_produire}",
    },
}


def _destinataires_du_champ(objet, chemin):
    valeur = objet
    for attribut in chemin.split("."):
        valeur = getattr(valeur, attribut, None)
        if valeur is None:
            return []
    if hasattr(valeur, "all"):   # relation multiple (ex : agents affectés)
        return list(valeur.all())
    return [valeur]


def notifier(titre, message="", document=None, profils=(), utilisateurs=()):
    """Crée une notification pour chaque destinataire actif (hors auteur de l'action)."""
    from apps.comptes.models import Utilisateur
    from .historique import utilisateur_courant
    from .models import Notification
    destinataires = {u.pk: u for u in utilisateurs if u is not None and u.is_active}
    if profils:
        for utilisateur in Utilisateur.objects.filter(profil__in=profils, is_active=True):
            destinataires[utilisateur.pk] = utilisateur
    auteur = utilisateur_courant()
    if auteur is not None:
        destinataires.pop(auteur.pk, None)
    type_document, document_id, reference = "", None, ""
    if document is not None:
        type_document = f"{document._meta.app_label}.{document._meta.model_name}"
        document_id = document.pk
        reference = str(getattr(document, "numero", "") or getattr(document, "numero_lot", "") or document.pk)
    Notification.objects.bulk_create([
        Notification(
            destinataire=destinataire, titre=titre[:150], message=message[:500],
            type_document=type_document, document_id=document_id, reference=reference,
        )
        for destinataire in destinataires.values()
    ])


def notifier_changement_statut(objet):
    regle = REGLES_STATUT.get((f"{objet._meta.app_label}.{objet._meta.model_name}", objet.statut))
    if regle is None:
        return
    try:
        message = regle.get("message", "").format(objet=objet)
    except (AttributeError, KeyError, ValueError):
        message = ""
    utilisateurs = _destinataires_du_champ(objet, regle["champ"]) if "champ" in regle else []
    notifier(regle["titre"], message, document=objet, profils=regle.get("profils", ()), utilisateurs=utilisateurs)
