"""
Tests : traçabilité lot -> client et sortie par DLC, palettes et
emplacements, déclencheurs de contrôle (cuve, quantité, nettoyage,
arrêt), exports qualité, unité d'achat, coût du changement de série.

Lancer : python manage.py test apps.industriel.tests_tracabilite
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.achats.models import (
    CommandeFournisseur, Fournisseur, LigneCommandeFournisseur, LigneReceptionAchat, ReceptionAchat, RetourFournisseur,
)
from apps.core.tests import BaseValidation
from apps.couts import cascade
from apps.couts.models import Charge
from apps.distribution.models import PreparationLivraison
from apps.industriel.models import Activite, EtapeStandard, Equipement, Usine
from apps.production.models import ChangementSerie, EtapeProduction, EvenementProduction, OrdreFabrication
from apps.qualite.models import Lot, ParametreQualite, PointControle, ResultatControle
from apps.referentiel.models import ConversionUnite
from apps.stocks.models import (
    Depot, Emplacement, LigneTransfert, LotMatiere, MouvementLot, Palette, StockArticle, TransfertStock, ValorisationArticle,
    depot_par_defaut,
)


class LotsProduitsFinisMixin:
    def lot_libere(self, quantite, peremption_dans_jours):
        lot = Lot.objects.create(
            article=self.produit, quantite=quantite, date_production=date.today(),
            date_peremption=date.today() + timedelta(days=peremption_dans_jours),
        )
        Lot.objects.filter(pk=lot.pk).update(statut="CONFORME")
        lot.refresh_from_db()
        lot.liberer(self.admin)
        return lot

    def vendre(self, quantite):
        commande = self.commande(lignes=((quantite, 100),), statut="VALIDEE")
        preparation = PreparationLivraison.objects.create(commande=commande, lancee_par=self.admin)
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_preparation/")
        r = self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/")
        return commande, r


class TracabiliteClientTests(LotsProduitsFinisMixin, BaseValidation):
    def setUp(self):
        super().setUp()
        self.lot_tardif = self.lot_libere(100, 90)
        self.lot_proche = self.lot_libere(50, 20)

    def test_vente_sort_la_dlc_la_plus_proche_et_garde_le_client(self):
        commande, r = self.vendre(70)
        self.assertEqual(r.status_code, 200, r.content)
        ventes = MouvementLot.objects.filter(ligne_commande__commande=commande)
        self.assertEqual({m.lot_id: -m.quantite for m in ventes}, {self.lot_proche.pk: 50, self.lot_tardif.pk: 20})
        rappel = self.api.get(f"/api/qualite/lots/{self.lot_tardif.id}/rappel/").data
        self.assertEqual(rappel["clients"][0]["client"], self.client_evam.nom)
        self.assertEqual(rappel["clients"][0]["quantite"], Decimal("20"))
        self.assertEqual(rappel["stock_restant"][0]["quantite"], Decimal("80"))

    def test_lot_bloque_ne_sort_plus_et_seul_le_reste_est_bloque(self):
        self.vendre(30)                       # 30 du lot le plus proche
        self.lot_proche.bloquer("NC")
        stock = StockArticle.objects.get(article=self.produit, depot=depot_par_defaut("Dépôt produits finis"))
        self.assertEqual(stock.quantite_bloquee, 20)
        _, r = self.vendre(110)               # 100 libres (lot tardif) : 110 impossible
        self.assertIn(r.status_code, (400, 409), r.content)
        _, r = self.vendre(90)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(MouvementLot.objects.filter(lot=self.lot_proche, quantite__lt=0).exclude(quantite=-30).exists())

    def test_transfert_suit_le_lot_jusqu_au_depot(self):
        nord = Depot.objects.create(nom="Dépôt Nord", type_lieu="DEPOT_EXTERIEUR")
        transfert = TransfertStock.objects.create(depot_source=depot_par_defaut("Dépôt produits finis"), depot_destination=nord, cree_par=self.admin)
        LigneTransfert.objects.create(transfert=transfert, article=self.produit, quantite=60)
        self.api.post(f"/api/stocks/transferts/{transfert.id}/expedier/")
        self.api.post(f"/api/stocks/transferts/{transfert.id}/receptionner/")
        lieux = {l["lieu"]: l["quantite"] for l in self.api.get(f"/api/qualite/lots/{self.lot_tardif.id}/tracabilite/").data["stock_restant"]}
        self.assertEqual(lieux, {"Dépôt produits finis": Decimal("90"), "Dépôt Nord": Decimal("10")})


class PalettesTests(LotsProduitsFinisMixin, BaseValidation):
    def setUp(self):
        super().setUp()
        self.produit.packs_par_palette = 10   # 10 packs de 8 = 80 bouteilles
        self.produit.save()
        self.lot = self.lot_libere(200, 60)
        self.lieu = depot_par_defaut("Dépôt produits finis")

    def test_palettisation_rangement_etiquette(self):
        r = self.api.post(f"/api/qualite/lots/{self.lot.id}/palettiser/")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual([Decimal(p["quantite"]) for p in r.data], [Decimal(80), Decimal(80), Decimal(40)])
        self.assert_refus(self.api.post(f"/api/qualite/lots/{self.lot.id}/palettiser/"))
        allee = Emplacement.objects.create(depot=self.lieu, designation="Allée A - niveau 1", capacite_palettes=1)
        premiere, deuxieme = Palette.objects.order_by("pk")[:2]
        self.assertEqual(self.api.post(f"/api/stocks/palettes/{premiere.id}/deplacer/", {"emplacement": allee.id}, format="json").status_code, 200)
        plein = self.assert_refus(self.api.post(f"/api/stocks/palettes/{deuxieme.id}/deplacer/", {"emplacement": allee.id}, format="json"))
        self.assertIn("plein", str(plein.data))
        etiquette = self.api.get(f"/api/stocks/palettes/{premiere.id}/etiquette/")
        self.assertEqual(etiquette["Content-Type"], "application/pdf")
        self.assertTrue(etiquette.content.startswith(b"%PDF"))

    def test_transfert_d_une_palette(self):
        self.api.post(f"/api/qualite/lots/{self.lot.id}/palettiser/")
        palette = Palette.objects.order_by("pk").first()
        nord = Depot.objects.create(nom="Dépôt Nord", type_lieu="DEPOT_EXTERIEUR")
        transfert = TransfertStock.objects.create(depot_source=self.lieu, depot_destination=nord, cree_par=self.admin)
        r = self.api.post("/api/stocks/lignes-transfert/", {"transfert": transfert.id, "palette": palette.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.data["quantite"]), Decimal(80))
        self.api.post(f"/api/stocks/transferts/{transfert.id}/expedier/")
        self.api.post(f"/api/stocks/transferts/{transfert.id}/receptionner/")
        palette.refresh_from_db()
        self.assertEqual((palette.depot, palette.statut), (nord, "EN_STOCK"))


class DeclencheursTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.eau = Activite.objects.get(code="EAU")
        self.aspect = ParametreQualite.objects.get(libelle="Aspect / couleur")
        self.cuve = Equipement.objects.create(designation="Cuve Eau 1", type_equipement="CUVE",
                                              usine=Usine.objects.get(code="US-EAU"), activite=self.eau)
        self.entree_stock(self.matiere, 20)
        self.of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        for _ in range(4):
            self.of.passer_statut_suivant()

    def point(self, declencheur, **autres):
        return PointControle.objects.create(designation=f"Contrôle {declencheur}", parametre=self.aspect, activite=self.eau,
                                            declencheur=declencheur, statut="ACTIF", **autres)

    def test_cuve_nettoyage_arret(self):
        cuve = self.point("CHAQUE_CUVE")
        nettoyage = self.point("APRES_NETTOYAGE")
        arret = self.point("APRES_ARRET")
        r = self.api.post("/api/production/evenements/", {
            "ordre_fabrication": self.of.id, "type_evenement": "CUVE", "equipement": self.cuve.id, "numero_cuve": "C-12",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        controle = ResultatControle.objects.get(point=cuve)
        self.assertEqual(controle.equipement, self.cuve)
        EvenementProduction.objects.create(ordre_fabrication=self.of, type_evenement="CUVE", equipement=self.cuve)
        self.assertEqual(ResultatControle.objects.filter(point=cuve).count(), 2)   # à chaque cuve
        EvenementProduction.objects.create(ordre_fabrication=self.of, type_evenement="NETTOYAGE")
        EvenementProduction.objects.create(ordre_fabrication=self.of, type_evenement="ARRET_REDEMARRAGE", duree_min=20)
        self.assertEqual(ResultatControle.objects.filter(point__in=[nettoyage, arret]).count(), 2)

    def test_tous_les_x_unites(self):
        point = self.point("PAR_QUANTITE", frequence_quantite=100, etape=EtapeStandard.objects.get(code="REMPLISSAGE"))
        EtapeProduction.objects.create(ordre_fabrication=self.of, etape="REMPLISSAGE", agent=self.admin, quantite_produite=250)
        self.assertEqual(ResultatControle.objects.filter(point=point).count(), 2)
        EtapeProduction.objects.create(ordre_fabrication=self.of, etape="REMPLISSAGE", agent=self.admin, quantite_produite=60)
        self.assertEqual(ResultatControle.objects.filter(point=point).count(), 3)
        EtapeProduction.objects.create(ordre_fabrication=self.of, etape="ETIQUETAGE", agent=self.admin, quantite_produite=500)
        self.assertEqual(ResultatControle.objects.filter(point=point).count(), 3)   # autre étape

    def test_quantite_obligatoire(self):
        r = self.assert_refus(self.api.post("/api/qualite/plan-controle/", {
            "designation": "Volume", "parametre": self.aspect.id, "activite": self.eau.id, "declencheur": "PAR_QUANTITE",
        }, format="json"))
        self.assertIn("frequence_quantite", r.data)

    def test_exports_excel_et_pdf(self):
        self.point("CHAQUE_CUVE")
        EvenementProduction.objects.create(ordre_fabrication=self.of, type_evenement="CUVE")
        for url in ("/api/qualite/controles-realises/export/?type=xlsx", "/api/qualite/indicateurs/?type=xlsx"):
            r = self.api.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertTrue(r.content.startswith(b"PK"), url)        # fichier xlsx (zip)
        for url in ("/api/qualite/controles-realises/export/?type=pdf", "/api/qualite/indicateurs/?type=pdf"):
            r = self.api.get(url)
            self.assertEqual(r["Content-Type"], "application/pdf", url)


class UniteAchatTests(BaseValidation):
    def setUp(self):
        super().setUp()
        ConversionUnite.objects.create(article=self.matiere, unite_source="SAC", facteur=25, unite_cible="KG")
        self.matiere.unite_achat = "SAC"
        self.matiere.save()
        self.commande_f = CommandeFournisseur.objects.create(fournisseur=Fournisseur.objects.create(code="F1", nom="Sucrerie"), cree_par=self.admin)
        self.ligne = LigneCommandeFournisseur.objects.create(commande=self.commande_f, article=self.matiere, quantite_commandee=10, prix_unitaire=15000)
        self.commande_f.envoyer()

    def test_commande_en_sacs_stock_en_kg(self):
        self.assertEqual(self.ligne.unite, "SAC")
        reception = ReceptionAchat.objects.create(commande=self.commande_f, receptionne_par=self.admin)
        LigneReceptionAchat.objects.create(reception=reception, ligne_commande=self.ligne, quantite_recue=4, lot_fournisseur="SB-778")
        stock = StockArticle.objects.get(article=self.matiere, depot=depot_par_defaut("Magasin principal"))
        self.assertEqual(stock.quantite_physique, Decimal(100))                       # 4 sacs = 100 kg
        self.assertEqual(ValorisationArticle.objects.get(article=self.matiere).cout_unitaire_moyen, Decimal(600))   # 15 000 / 25
        self.assertEqual(LotMatiere.objects.get(lot_fournisseur="SB-778").quantite_initiale, Decimal(100))
        RetourFournisseur.objects.create(reception=reception, article=self.matiere, quantite_retournee=1, motif="ENDOMMAGE", traite_par=self.admin)
        stock.refresh_from_db()
        self.assertEqual(stock.quantite_physique, Decimal(75))
        self.assert_refus(self.api.post("/api/achats/lignes-reception/", {
            "reception": reception.id, "ligne_commande": self.ligne.id, "quantite_recue": 7,   # reste 6 sacs
        }, format="json"))

    def test_unite_sans_conversion_refusee(self):
        commande = CommandeFournisseur.objects.create(fournisseur=Fournisseur.objects.get(code="F1"), cree_par=self.admin)
        r = self.assert_refus(self.api.post("/api/achats/lignes-commande/", {
            "commande": commande.id, "article": self.matiere.id, "unite": "PALETTE", "quantite_commandee": 1, "prix_unitaire": 1,
        }, format="json"))
        self.assertIn("conversion", str(r.data))


class CoutChangementSerieTests(BaseValidation):
    def test_nettoyage_impute_directement_a_l_of(self):
        periode = timezone.localdate().strftime("%Y-%m")
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="EN_PRODUCTION")
        of.refresh_from_db()
        changement = ChangementSerie.objects.create(ordre_fabrication=of, date_debut=timezone.now(), duree_arret_min=30, cout_nettoyage=5000)
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="CLOTURE", date_fin=timezone.now())
        cascade.calculer_periode(periode)
        charge = Charge.objects.get(source=f"{cascade.SOURCE_CHANGEMENT_SERIE}{changement.pk}")
        self.assertEqual((charge.ordre_fabrication_id, charge.montant, charge.statut_repartition), (of.pk, Decimal(5000), "REPARTIE"))
        revient = cascade.cout_revient(periode)
        self.assertEqual(revient["ofs"][0]["dont_changement_serie"], Decimal("5000.00"))
        ChangementSerie.objects.filter(pk=changement.pk).update(cout_nettoyage=None)
        cascade.calculer_periode(periode)
        self.assertFalse(Charge.objects.filter(source=f"{cascade.SOURCE_CHANGEMENT_SERIE}{changement.pk}").exists())
