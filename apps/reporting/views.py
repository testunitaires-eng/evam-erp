"""
Vues du module reporting.

Chaque bloc du tableau de bord Direction (§12.2) est calculé par sa
propre fonction, exposée à la fois séparément (une route par rubrique,
§12.1) et regroupée sur /tableau-de-bord-direction/.

Hypothèses de calcul posées faute de précision dans le document (à
valider avec le client, chacune documentée sur place) :
- "Production conforme" = quantité des lots au statut LIBERE ou
  CONFORME (apps.qualite.Lot), toutes familles de produits confondues
  (pas seulement l'eau).
- "Valeur du stock" = quantité physique x dernier coût unitaire connu
  (apps.couts.CoutMatiere) ; 0 si aucun coût n'a jamais été renseigné
  pour l'article.
- "Solde théorique caisse" = solde d'ouverture + encaissements des
  sessions ouvertes aujourd'hui (pas de décaissements distincts : ce
  modèle n'existe pas encore dans le backend, voir README).
- "Livraison en retard" = bon de livraison encore En livraison, généré
  il y a plus d'un jour.
"""

from datetime import date
from django.db.models import Sum, F, Count
from rest_framework.decorators import api_view, permission_classes as drf_permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import viewsets
from apps.comptes.permissions import role_required
from apps.comptes.models import Profil
from . import models, serializers


def _bloc_production():
    """§12.2.1 - Production."""
    from apps.qualite.models import Lot
    from apps.production.models import PerteProduction, OrdreFabrication

    aujourd_hui = date.today()
    debut_mois = aujourd_hui.replace(day=1)

    def stats_periode(depuis):
        conforme = Lot.objects.filter(
            statut__in=["LIBERE", "CONFORME"], date_production__gte=depuis
        ).aggregate(total=Sum("quantite"))["total"] or 0
        pertes = PerteProduction.objects.filter(
            date_constat__date__gte=depuis
        ).aggregate(total=Sum("quantite_perte"))["total"] or 0
        production_prevue = OrdreFabrication.objects.filter(
            date_creation__date__gte=depuis
        ).aggregate(total=Sum("quantite_a_produire"))["total"] or 0
        rendement = round(float(conforme) / float(production_prevue) * 100, 2) if production_prevue else None
        taux_perte = round(float(pertes) / float(production_prevue) * 100, 2) if production_prevue else None
        return {
            "production_conforme": conforme,
            "rendement_pourcentage": rendement,
            "pertes_pourcentage": taux_perte,
        }

    return {
        "aujourd_hui": stats_periode(aujourd_hui),
        "mois": stats_periode(debut_mois),
    }


def _bloc_stock():
    """§12.2.2 - Stock."""
    from apps.stocks.models import StockArticle
    from apps.couts.models import CoutMatiere
    from apps.referentiel.models import Article, TypeArticle

    def valeur_stock(type_article):
        total = 0
        for stock in StockArticle.objects.filter(article__type_article=type_article).select_related("article"):
            dernier_cout = (
                CoutMatiere.objects.filter(article=stock.article)
                .order_by("-date_valorisation").first()
            )
            if dernier_cout:
                total += float(stock.quantite_physique) * float(dernier_cout.cout_unitaire)
        return round(total, 2)

    articles_rupture = 0
    articles_sous_minimum = 0
    for stock in StockArticle.objects.select_related("article"):
        if stock.quantite_disponible <= 0:
            articles_rupture += 1
        elif stock.article.stock_minimum and stock.quantite_disponible < stock.article.stock_minimum:
            articles_sous_minimum += 1

    return {
        "valeur_stock_matieres": valeur_stock(TypeArticle.MATIERE_PREMIERE),
        "valeur_stock_produits_finis": valeur_stock(TypeArticle.PRODUIT_FINI),
        "articles_en_rupture": articles_rupture,
        "articles_sous_minimum": articles_sous_minimum,
    }


def _bloc_commercial():
    """§12.2.3 - Ventes."""
    from apps.commercial.models import Facture, LigneFacture

    aujourd_hui = date.today()
    debut_mois = aujourd_hui.replace(day=1)

    ca_jour = Facture.objects.filter(date_emission__date=aujourd_hui).aggregate(
        total=Sum("montant_total"))["total"] or 0
    ca_mois = Facture.objects.filter(date_emission__date__gte=debut_mois).aggregate(
        total=Sum("montant_total"))["total"] or 0

    produit_top = (
        LigneFacture.objects.filter(facture__date_emission__date__gte=debut_mois)
        .values("article__code").annotate(total=Sum("quantite"))
        .order_by("-total").first()
    )
    client_top = (
        Facture.objects.filter(date_emission__date__gte=debut_mois)
        .values("client__nom").annotate(total=Sum("montant_total"))
        .order_by("-total").first()
    )

    return {
        "chiffre_affaires_jour": ca_jour,
        "chiffre_affaires_mois": ca_mois,
        "produit_le_plus_vendu": produit_top["article__code"] if produit_top else None,
        "client_principal": client_top["client__nom"] if client_top else None,
    }


# def _bloc_caisse():
#     """§12.2.4 - Caisse."""
#     from apps.caisse.models import SessionCaisse, Encaissement, EcartCaisse

#     aujourd_hui = date.today()
#     encaissements_jour = Encaissement.objects.filter(
#         date_encaissement__date=aujourd_hui
#     ).aggregate(total=Sum("montant"))["total"] or 0

#     sessions_jour = SessionCaisse.objects.filter(date_ouverture__date=aujourd_hui)
#     solde_theorique = sessions_jour.aggregate(total=Sum("solde_ouverture"))["total"] or 0
#     solde_theorique = float(solde_theorique) + float(encaissements_jour)

#     ecarts_jour = EcartCaisse.objects.filter(
#         session_caisse__in=sessions_jour
#     ).aggregate(total=Sum("montant_ecart"))["total"] or 0

#     return {
#         "encaissements_jour": encaissements_jour,
#         "solde_theorique": round(solde_theorique, 2),
#         "ecart_caisse": ecarts_jour,
#     }


def _bloc_caisse():
    """§12.2.4 - Caisse."""
    from apps.caisse.models import SessionCaisse, Encaissement, EcartCaisse

    aujourd_hui = date.today()
    encaissements_jour = Encaissement.objects.filter(
        date_encaissement__date=aujourd_hui
    ).aggregate(total=Sum("montant"))["total"] or 0

    sessions_jour = SessionCaisse.objects.filter(date_ouverture__date=aujourd_hui)
    solde_theorique = sum((s.calculer_solde_theorique() for s in sessions_jour), start=0)

    ecarts_jour = EcartCaisse.objects.filter(
        session_caisse__in=sessions_jour
    ).aggregate(total=Sum("montant_ecart"))["total"] or 0

    return {
        "encaissements_jour": encaissements_jour,
        "solde_theorique": round(float(solde_theorique), 2),
        "ecart_caisse": ecarts_jour,
    }

def _bloc_distribution():
    """§12.2.5 - Distribution."""
    from apps.distribution.models import BonLivraison
    from django.utils import timezone

    aujourd_hui = date.today()
    bl_jour = BonLivraison.objects.filter(date_generation__date=aujourd_hui)
    en_retard = BonLivraison.objects.filter(
        statut="EN_LIVRAISON", date_generation__date__lt=aujourd_hui
    ).count()

    return {
        "livraisons_prevues": bl_jour.count(),
        "livraisons_terminees": bl_jour.filter(statut="LIVREE").count(),
        "livraisons_en_cours": bl_jour.filter(statut="EN_LIVRAISON").count(),
        "livraisons_en_retard": en_retard,
    }


def _bloc_rentabilite():
    """§12.2.6 - Rentabilité."""
    from apps.couts.models import CoutReel
    from apps.commercial.models import LigneFacture

    produits = []
    for cout_reel in CoutReel.objects.select_related("ordre_fabrication__article").order_by("-date_calcul")[:20]:
        article = cout_reel.ordre_fabrication.article
        derniere_ligne = (
            LigneFacture.objects.filter(article=article).order_by("-facture__date_emission").first()
        )
        if not derniere_ligne:
            continue
        prix_vente = float(derniere_ligne.prix_unitaire_ht)
        cout_unitaire = float(cout_reel.cout_unitaire_reel)
        marge = prix_vente - cout_unitaire
        produits.append({
            "produit": article.code,
            "cout_de_revient": round(cout_unitaire, 2),
            "prix_de_vente": round(prix_vente, 2),
            "marge": round(marge, 2),
            "taux_marge_pourcentage": round(marge / prix_vente * 100, 2) if prix_vente else None,
        })
    produits.sort(key=lambda p: p["marge"], reverse=True)

    marge_moyenne = (
        round(sum(p["taux_marge_pourcentage"] for p in produits if p["taux_marge_pourcentage"] is not None) / len(produits), 2)
        if produits else None
    )

    return {
        "produits_les_plus_rentables": produits[:10],
        "marge_moyenne_pourcentage": marge_moyenne,
    }


def _bloc_alertes():
    """§12.1 - Alertes : consolide les signaux déjà remontés par chaque module."""
    from apps.production.views import tableau_de_bord as _  # noqa: import pour clarté du couplage
    from apps.production.models import BesoinMatierePrevu, StatutOF
    from apps.stocks.models import StockArticle
    from apps.caisse.models import SessionCaisse
    from apps.comptabilite.models import AnomalieDetectee

    matieres_manquantes = [
        {"of": b.ordre_fabrication.numero, "matiere": b.matiere.code, "manquant": b.manquant()}
        for b in BesoinMatierePrevu.objects.select_related("matiere", "ordre_fabrication")
        .exclude(ordre_fabrication__statut__in=[StatutOF.CLOTURE, StatutOF.ANNULE])
        if b.situation() == "Insuffisant"
    ]
    ruptures_stock = [
        {"article": s.article.code, "depot": s.depot.nom}
        for s in StockArticle.objects.select_related("article", "depot")
        if s.quantite_disponible <= 0
    ]
    sessions_sans_justification = [
        {"session_id": s.id, "caisse": s.caisse.nom, "ecart": s.ecart}
        for s in SessionCaisse.objects.filter(statut="CLOTUREE").select_related("caisse")
        if s.ecart and s.ecart != 0 and not hasattr(s, "justification_ecart")
    ]
    anomalies_comptables = list(
        AnomalieDetectee.objects.filter(statut="DETECTEE").values(
            "id", "type_anomalie", "module_source", "description"
        )
    )

    return {
        "matieres_manquantes": matieres_manquantes,
        "ruptures_stock": ruptures_stock,
        "ecarts_caisse_non_justifies": sessions_sans_justification,
        "anomalies_comptables": anomalies_comptables,
    }


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def tableau_de_bord_direction(request):
    """
    GET /api/reporting/tableau-de-bord-direction/

    §12.2 : le tableau de bord consolidé, un bloc par rubrique. Chaque
    bloc est aussi accessible séparément (voir urls.py) pour les
    écrans dédiés à un seul module.
    """
    return Response({
        "production": _bloc_production(),
        "stock": _bloc_stock(),
        "commercial": _bloc_commercial(),
        "caisse": _bloc_caisse(),
        "distribution": _bloc_distribution(),
        "rentabilite": _bloc_rentabilite(),
        "alertes": _bloc_alertes(),
    })


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def bloc_production(request):
    return Response(_bloc_production())


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def bloc_stock(request):
    return Response(_bloc_stock())


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def bloc_commercial(request):
    return Response(_bloc_commercial())


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def bloc_caisse(request):
    return Response(_bloc_caisse())


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def bloc_distribution(request):
    return Response(_bloc_distribution())


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def bloc_rentabilite(request):
    return Response(_bloc_rentabilite())


@api_view(["GET"])
@drf_permission_classes([IsAuthenticated])
def bloc_alertes(request):
    return Response(_bloc_alertes())


class RapportGenereViewSet(viewsets.ModelViewSet):
    """§12.1 - Rapports périodiques : instantanés figés du tableau de bord."""
    queryset = models.RapportGenere.objects.all()
    serializer_class = serializers.RapportGenereSerializer
    permission_classes = [role_required(Profil.DIRECTION, Profil.COMPTABILITE_DAF, Profil.ADMIN_SI)]
    filterset_fields = ["periode", "date_rapport"]

    def perform_create(self, serializer):
        serializer.save(genere_par=self.request.user)

    @action(detail=False, methods=["post"])
    def generer_aujourd_hui(self, request):
        """
        POST /api/reporting/rapports/generer_aujourd_hui/
        Corps : {"periode": "JOURNALIER"|"MENSUEL"}
        Fige le tableau de bord Direction actuel dans un RapportGenere.
        """
        periode = request.data.get("periode", "JOURNALIER")
        contenu = tableau_de_bord_direction(request._request).data
        rapport, cree = models.RapportGenere.objects.update_or_create(
            periode=periode, date_rapport=date.today(),
            defaults={"contenu": contenu, "genere_par": request.user},
        )
        return Response(self.get_serializer(rapport).data, status=201 if cree else 200)