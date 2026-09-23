"""
Signal qui répercute automatiquement tout MouvementStock sur le
StockArticle correspondant, quel que soit le module qui crée le
mouvement (production, achats, qualité, distribution, réclamations,
ou directement via l'API /api/stocks/mouvements/).

AVANT ce fichier, cette mise à jour ne se produisait QUE lors d'un
POST direct sur /api/stocks/mouvements/ (elle était codée en dur
dans MouvementStockViewSet.perform_create, voir apps/stocks/views.py).
Tout mouvement créé ailleurs dans le projet (ORM direct depuis
apps.production, apps.qualite, apps.achats, apps.reclamations...)
n'avait donc AUCUN effet réel sur le stock, malgré des commentaires
dans models.py/views.py qui prétendaient déjà le contraire ("voir
signal dans apps/stocks/signals.py" - ce fichier n'existait pas).

Ce module est chargé au démarrage de Django via apps/stocks/apps.py
(StocksConfig.ready()).
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import MouvementStock, StockArticle


@receiver(post_save, sender=MouvementStock)
def appliquer_mouvement_au_stock(sender, instance, created, **kwargs):
    """
    Un MouvementStock est un fait historique : on ne réapplique donc
    jamais un mouvement modifié après coup (created=False est ignoré).
    Personne dans le projet ne modifie un mouvement existant
    aujourd'hui, mais si c'était le cas, le réappliquer ici doublerait
    l'effet sur le stock - mieux vaut l'ignorer explicitement.
    """
    if not created:
        return

    stock, _ = StockArticle.objects.select_for_update().get_or_create(
        article=instance.article, depot=instance.depot,
    )
    if instance.type_mouvement in ("ENTREE", "RETOUR", "AJUSTEMENT"):
        stock.quantite_physique += instance.quantite
    elif instance.type_mouvement == "SORTIE":
        stock.quantite_physique -= instance.quantite
    stock.save()