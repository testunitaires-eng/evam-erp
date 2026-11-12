"""
Valorisation des sorties de stock du forage et du traitement de l'eau
(sel, produits de lavage, kits, pièces, carburant) pour le coût de l'eau.

PEPS / FIFO (méthode retenue, à confirmer avec l'expert-comptable) : on
rejoue l'historique de l'article, tous dépôts confondus, dans l'ordre
des mouvements. Chaque entrée (achat, retour, ajustement positif) ajoute
une couche à son coût ; chaque sortie (ou ajustement négatif) consomme
d'abord la couche la plus ancienne. Les transferts entre dépôts sont
ignorés (la marchandise reste dans l'entreprise, ses couches gardent
leur ordre d'achat).

Seul le coût de l'eau utilise cette valeur : la valeur comptable du
stock et des mouvements reste au CMUP du module Stocks. Le paramètre
« valorisation des sorties de stock » (PEPS ou CMUP) permet de suivre
la décision de l'expert-comptable sans rien recalculer des mois clôturés.

Sortie sans couche suffisante (stock initial jamais entré dans le
logiciel) : la part manquante est valorisée au CMUP de la sortie, avec
une alerte.
"""

from collections import deque
from decimal import Decimal

ZERO = Decimal(0)


def valeurs_peps(article, jusqu_au=None):
    """{id du mouvement de sortie: (valeur PEPS, quantité sans couche)} pour l'article."""
    from apps.stocks.models import MouvementStock, TransfertStock, TypeMouvement
    mouvements = MouvementStock.objects.filter(article=article)
    if jusqu_au is not None:
        mouvements = mouvements.filter(date_mouvement__lte=jusqu_au)
    transferts = set(TransfertStock.objects.filter(
        numero__in=mouvements.exclude(document_origine="").values("document_origine"),
    ).values_list("numero", flat=True))
    couches, valeurs = deque(), {}
    for mouvement in mouvements.order_by("date_mouvement", "pk"):
        if mouvement.document_origine in transferts:
            continue
        quantite = Decimal(mouvement.quantite)
        entree = mouvement.type_mouvement in (TypeMouvement.ENTREE, TypeMouvement.RETOUR) or (
            mouvement.type_mouvement == TypeMouvement.AJUSTEMENT and quantite > 0
        )
        if entree:
            couches.append([quantite, Decimal(mouvement.cout_unitaire or 0)])
            continue
        reste, valeur = abs(quantite), ZERO
        while reste > 0 and couches:
            couche = couches[0]
            prise = min(reste, couche[0])
            valeur += prise * couche[1]
            couche[0] -= prise
            reste -= prise
            if couche[0] == 0:
                couches.popleft()
        if reste > 0:
            valeur += reste * Decimal(mouvement.cout_unitaire or 0)
        valeurs[mouvement.pk] = (valeur, reste)
    return valeurs


def consommations_du_mois(usine, mois, methode):
    """
    Sorties de stock (moins les retours) vers les éléments du coût de l'eau
    du site, au mois de la sortie : ({élément: valeur}, [lignes de détail], [alertes]).
    """
    from apps.stocks.models import MouvementStock, TypeMouvement
    from .models import ValorisationStock
    annee, numero = (int(x) for x in mois.split("-"))
    mouvements = MouvementStock.objects.filter(
        element_eau__usine=usine, date_mouvement__year=annee, date_mouvement__month=numero,
        type_mouvement__in=(TypeMouvement.SORTIE, TypeMouvement.RETOUR),
    ).select_related("article", "element_eau__etape__sous_etape_de").order_by("date_mouvement", "pk")
    par_element, lignes, alertes, cache = {}, [], [], {}
    for mouvement in mouvements:
        if mouvement.type_mouvement == TypeMouvement.RETOUR:
            valeur = Decimal(mouvement.quantite) * Decimal(mouvement.cout_unitaire or 0)
            valeur = -valeur
        elif methode == ValorisationStock.PEPS:
            if mouvement.article_id not in cache:
                cache[mouvement.article_id] = valeurs_peps(mouvement.article)
            valeur, manque = cache[mouvement.article_id][mouvement.pk]
            if manque:
                alertes.append(
                    f"{mouvement.numero} ({mouvement.article.code}) : {format(manque.normalize(), 'f')} sans entrée en stock "
                    "enregistrée, valorisé(s) au CMUP."
                )
        else:
            valeur = Decimal(mouvement.valeur or 0)
        element = mouvement.element_eau
        par_element[element] = par_element.get(element, ZERO) + valeur
        lignes.append({
            "mouvement": mouvement.numero, "date": str(mouvement.date_mouvement.date()), "article": mouvement.article.code,
            "type": mouvement.type_mouvement, "quantite": format(Decimal(mouvement.quantite).normalize(), "f"),
            "element": element.libelle, "valeur": str(valeur.quantize(Decimal("0.01"))),
            "valeur_cmup": str(Decimal(mouvement.valeur or 0).quantize(Decimal("0.01"))) if mouvement.type_mouvement == TypeMouvement.SORTIE else None,
        })
    return par_element, lignes, alertes
