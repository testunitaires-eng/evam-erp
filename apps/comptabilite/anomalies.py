"""
Détection automatique des anomalies (§14.3) :
- à l'événement (appelé par les documents) : écart de caisse à la
  clôture, écart d'inventaire, dépassement de consommation matière ;
- par contrôle périodique (detecter_anomalies, commande
  « python manage.py detecter_anomalies » à planifier chaque jour, ou
  bouton « Lancer la détection » de la Comptabilité/DAF).
Une anomalie n'est créée qu'une fois tant qu'elle est ouverte (clé), la
Comptabilité/DAF et la Direction sont notifiées, et les anomalies
périodiques dont la cause a disparu (facture payée, stock refait...)
sont résolues automatiquement.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from .models import AnomalieDetectee, CleControle, ParametreControle, StatutAnomalie, TypeAnomalie


def seuil(cle):
    """Seuil courant réglé par la Comptabilité/DAF (/api/comptabilite/seuils-controles/)."""
    return ParametreControle.valeur_de(cle)

STATUTS_OUVERTS = (StatutAnomalie.DETECTEE, StatutAnomalie.EN_TRAITEMENT)
TYPES_PERIODIQUES = (
    TypeAnomalie.IMPAYE, TypeAnomalie.STOCK_SOUS_MINIMUM, TypeAnomalie.LOT_PERIME,
    TypeAnomalie.SESSION_NON_CLOTUREE, TypeAnomalie.DECAISSEMENT_EN_ATTENTE,
)


def signaler_anomalie(type_anomalie, module, description, cle, document=None):
    """Crée l'anomalie (sauf si la même est déjà ouverte) et prévient la DAF et la Direction."""
    from apps.comptes.models import Profil
    from apps.core.notifications import notifier
    if AnomalieDetectee.objects.filter(cle=cle, statut__in=STATUTS_OUVERTS).exists():
        return None
    anomalie = AnomalieDetectee.objects.create(
        type_anomalie=type_anomalie, module_source=module, description=description, cle=cle,
        type_document=f"{document._meta.app_label}.{document._meta.model_name}" if document is not None else "",
        document_id=document.pk if document is not None else None,
        reference=str(getattr(document, "numero", "") or getattr(document, "numero_lot", "") or "") if document is not None else "",
    )
    notifier(
        f"Anomalie : {anomalie.get_type_anomalie_display()}", description,
        document=anomalie, profils=[Profil.COMPTABILITE_DAF, Profil.DIRECTION],
    )
    return anomalie


# ----------------------------------------------------------- à l'événement

def controler_ecart_caisse(session):
    if session.ecart:
        signaler_anomalie(
            TypeAnomalie.ECART_CAISSE, "Caisse",
            f"Écart de {session.ecart} FCFA à la clôture de {session.caisse.nom} ({session.caissier.username}) - "
            f"justification : {session.justification_ecart.justification}",
            cle=f"ecart-caisse-{session.pk}", document=session,
        )


def controler_inventaire(inventaire):
    for ligne in inventaire.lignes.select_related("article"):
        if ligne.ecart:
            signaler_anomalie(
                TypeAnomalie.ECART_STOCK, "Stocks",
                f"Inventaire {inventaire.depot.nom} du {inventaire.date_inventaire} : {ligne.article.code} "
                f"théorique {ligne.quantite_theorique}, compté {ligne.quantite_comptee} (écart {ligne.ecart}).",
                cle=f"inventaire-{inventaire.pk}-{ligne.article_id}", document=inventaire,
            )


def controler_consommation_of(of):
    tolerance = seuil(CleControle.TOLERANCE_DEPASSEMENT_MATIERE)
    for matiere in of.calculer_consommation_reelle():
        pourcentage = matiere["ecart_pourcentage"]
        if pourcentage is not None and pourcentage > tolerance:
            signaler_anomalie(
                TypeAnomalie.DEPASSEMENT_MATIERE, "Production",
                f"OF {of.numero} : {matiere['matiere']} consommé {matiere['reelle']} pour {matiere['theorique']} "
                f"prévus (+{pourcentage:.1f} %, tolérance {tolerance} %).",
                cle=f"depassement-{of.pk}-{matiere['matiere']}", document=of,
            )


# ----------------------------------------------------------- contrôle périodique

def _cas_detectes():
    """Liste des (type, module, description, clé, document) constatés maintenant."""
    from django.db.models import F, Sum
    from apps.caisse.models import Decaissement, SessionCaisse, StatutDecaissement, StatutSession
    from apps.commercial.models import Facture, StatutFacture
    from apps.qualite.models import Lot, StatutLot
    from apps.referentiel.models import Article
    from apps.stocks.models import StockArticle

    aujourd_hui = timezone.localdate()
    cas = []
    for facture in Facture.objects.exclude(statut__in=[StatutFacture.ANNULEE, StatutFacture.PAYEE]).select_related("client"):
        if facture.est_impayee:
            cas.append((TypeAnomalie.IMPAYE, "Commercial",
                        f"Facture {facture.numero} ({facture.client.nom}) : {facture.solde_restant} FCFA impayés, "
                        f"{facture.jours_retard} jour(s) de retard.", f"impaye-{facture.pk}", facture))
    for article in Article.objects.filter(actif=True, stock_minimum__gt=0):
        disponible = StockArticle.objects.filter(article=article).aggregate(
            total=Sum(F("quantite_physique") - F("quantite_bloquee") - F("quantite_reservee")),
        )["total"] or 0
        if disponible < article.stock_minimum:
            cas.append((TypeAnomalie.STOCK_SOUS_MINIMUM, "Stocks",
                        f"{article.code} - {article.designation} : disponible {disponible}, minimum {article.stock_minimum}.",
                        f"stock-minimum-{article.pk}", article))
    limite = aujourd_hui + timedelta(days=int(seuil(CleControle.DELAI_ALERTE_PEREMPTION_JOURS)))
    for lot in Lot.objects.filter(statut=StatutLot.LIBERE, date_peremption__lte=limite).select_related("article"):
        etat = "périmé" if lot.date_peremption < aujourd_hui else f"périme le {lot.date_peremption:%d/%m/%Y}"
        cas.append((TypeAnomalie.LOT_PERIME, "Qualité", f"Lot {lot.numero_lot} ({lot.article.designation}) {etat}.",
                    f"peremption-{lot.pk}", lot))
    for session in SessionCaisse.objects.filter(statut=StatutSession.OUVERTE, date_ouverture__date__lt=aujourd_hui).select_related("caisse", "caissier"):
        cas.append((TypeAnomalie.SESSION_NON_CLOTUREE, "Caisse",
                    f"Session de {session.caisse.nom} ({session.caissier.username}) ouverte le "
                    f"{timezone.localtime(session.date_ouverture):%d/%m/%Y} et non clôturée.", f"session-ouverte-{session.pk}", session))
    jours_attente = int(seuil(CleControle.DELAI_DECAISSEMENT_EN_ATTENTE_JOURS))
    date_limite = timezone.now() - timedelta(days=jours_attente)
    for decaissement in Decaissement.objects.filter(statut=StatutDecaissement.EN_ATTENTE, date_decaissement__lt=date_limite):
        cas.append((TypeAnomalie.DECAISSEMENT_EN_ATTENTE, "Caisse",
                    f"Décaissement {decaissement.numero} ({decaissement.montant} FCFA) en attente d'autorisation "
                    f"depuis plus de {jours_attente} jours.", f"decaissement-attente-{decaissement.pk}", decaissement))
    return cas


def detecter_anomalies():
    """Lance les contrôles périodiques ; retourne (créées, résolues automatiquement)."""
    cas = _cas_detectes()
    creees = sum(1 for type_anomalie, module, description, cle, document in cas
                 if signaler_anomalie(type_anomalie, module, description, cle, document))
    cles_actuelles = {c[3] for c in cas}
    resolues = 0
    for anomalie in AnomalieDetectee.objects.filter(type_anomalie__in=TYPES_PERIODIQUES, statut__in=STATUTS_OUVERTS):
        if anomalie.cle not in cles_actuelles:
            anomalie.statut = StatutAnomalie.TRAITEE
            anomalie.date_traitement = timezone.now()
            anomalie.commentaire_traitement = "Résolue automatiquement : la situation n'est plus constatée."
            anomalie.save()
            resolues += 1
    return creees, resolues
