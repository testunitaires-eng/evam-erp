"""
Tests du socle industriel, des recettes, des lots matières, du module
Contrôle qualité et des coûts en cascade (documents EVAM de paramétrage,
de circuit, de contrôle qualité et de calcul des coûts).

Lancer : python manage.py test apps.industriel
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.tests import BaseValidation
from apps.couts import cascade
from apps.couts.models import Charge, NatureCout, RepartitionCout
from apps.industriel.models import Activite, Circuit, EtapeCircuit, EtapeStandard, Ligne, Usine
from apps.production.models import (
    ConsommationLotMatiere, EtapeProduction, OrdreFabrication, ParametreProduction, RetourMatiere, SortieMatiere,
    SuiviEau,
)
from apps.qualite.models import (
    Instrument, Lot, NonConformite, ParametreQualite, PointControle, ResultatControle,
)
from apps.referentiel.models import (
    Article, CompositionFicheTechnique, ConversionUnite, FicheTechnique,
)
from apps.stocks.models import (
    Depot, LigneTransfert, LotMatiere, StockArticle, TransfertStock, depot_par_defaut,
)


class SocleTests(BaseValidation):
    def test_parametrage_de_reference_installe(self):
        """Les 3 activités, 2 usines, les étapes et un circuit validé par activité existent."""
        self.assertEqual(set(Activite.objects.values_list("code", flat=True)), {"EAU", "JUS", "YAOURT"})
        self.assertEqual(Usine.objects.get(code="US-JY").activites.count(), 2)
        for code in ("EAU", "JUS", "YAOURT"):
            self.assertTrue(Circuit.objects.filter(activite__code=code, statut="VALIDE").exists())
        yaourt = Circuit.objects.get(activite__code="YAOURT", statut="VALIDE")
        self.assertFalse(yaourt.etapes.filter(etape__code="SOUFFLAGE").exists())   # pas de soufflage pour le yaourt
        self.assertTrue(NatureCout.objects.filter(inducteur="VOLUME_EAU_M3").exists())

    def test_produit_fini_rattache_et_quantites_deduites(self):
        """Famille Eau -> activité EAU ; 70 cl -> 0,7 L ; Pack de 8 -> 8 unités par pack."""
        self.assertEqual(self.produit.activite.code, "EAU")
        self.assertEqual(self.produit.contenance, Decimal("0.7"))
        self.assertEqual(self.produit.unites_par_pack, 8)
        self.assertEqual(self.produit.en_packs(80), Decimal(10))

    def test_of_recoit_le_circuit_de_son_activite(self):
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        self.assertEqual(of.circuit.activite.code, "EAU")
        self.assertEqual(of.fiche_technique.article, self.produit)

    def test_ligne_incompatible_refusee(self):
        usine = Usine.objects.get(code="US-JY")
        ligne_jus = Ligne.objects.create(designation="Ligne Jus 1", usine=usine, activite=Activite.objects.get(code="JUS"))
        r = self.assert_refus(self.api.post("/api/production/ordres-fabrication/", {
            "article": self.produit.id, "quantite_a_produire": 10, "ligne": ligne_jus.id,
        }, format="json"))
        self.assertIn("ligne", str(r.data))
        self.assertFalse(OrdreFabrication.objects.exists())

    def test_ligne_hors_usine_de_l_activite_refusee(self):
        r = self.assert_refus(self.api.post("/api/industriel/lignes/", {
            "designation": "Ligne Eau", "usine": Usine.objects.get(code="US-JY").id,
            "activite": Activite.objects.get(code="EAU").id,
        }, format="json"))
        self.assertIn("activite", r.data)

    def test_ligne_codifiee_automatiquement(self):
        r = self.api.post("/api/industriel/lignes/", {
            "designation": "Ligne Eau 1", "usine": Usine.objects.get(code="US-EAU").id,
            "activite": Activite.objects.get(code="EAU").id, "formats_compatibles": [self.produit.id],
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["code"], "LIG-EAU-01")

    def test_etape_hors_circuit_refusee(self):
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="EN_PRODUCTION")
        r = self.assert_refus(self.api.post("/api/production/etapes/", {
            "ordre_fabrication": of.id, "etape": "PREPARATION",
        }, format="json"))
        self.assertIn("circuit", str(r.data))
        ok = self.api.post("/api/production/etapes/", {
            "ordre_fabrication": of.id, "etape": "EMBOUTEILLAGE", "quantite_entree": 10, "quantite_produite": 9,
        }, format="json")
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(ok.data["etape"], "REMPLISSAGE")   # ancien code accepté

    def test_circuit_valide_fige(self):
        circuit = Circuit.objects.get(activite__code="EAU", statut="VALIDE")
        r = self.assert_refus(self.api.post("/api/industriel/etapes-circuit/", {
            "circuit": circuit.id, "etape": EtapeStandard.objects.get(code="PREPARATION").id, "ordre": 999,
        }, format="json"))
        self.assertIn("brouillon", str(r.data))
        copie = self.api.post(f"/api/industriel/circuits/{circuit.id}/nouvelle_version/")
        self.assertEqual(copie.status_code, 201)
        self.assertEqual(copie.data["version"], 2)
        self.assertEqual(len(copie.data["etapes"]), circuit.etapes.count())


class LancementTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)

    def test_lancement_bloque_si_stock_insuffisant(self):
        r = self.assert_refus(self.api.post(f"/api/production/ordres-fabrication/{self.of.id}/avancer_statut/"))
        self.assertIn("stock insuffisant", str(r.data))
        self.of.refresh_from_db()
        self.assertEqual(self.of.statut, "BROUILLON")
        verif = self.api.get(f"/api/production/ordres-fabrication/{self.of.id}/verifier_stock/").data
        self.assertFalse(verif["lancement_possible"])
        self.assertEqual(verif["manques"][0]["manquant"], Decimal("20"))

    def test_lancement_possible_avec_stock_ou_blocage_desactive(self):
        self.entree_stock(self.matiere, 20)
        r = self.api.post(f"/api/production/ordres-fabrication/{self.of.id}/avancer_statut/")
        self.assertEqual(r.status_code, 200, r.content)
        autre = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=100, responsable=self.admin)
        ParametreProduction.objects.update_or_create(pk=1, defaults={"bloquer_lancement_stock_insuffisant": False})
        r = self.api.post(f"/api/production/ordres-fabrication/{autre.id}/avancer_statut/")
        self.assertEqual(r.status_code, 200, r.content)


class RecetteTests(BaseValidation):
    """Recette « pour 1 000 L », emballages par bouteille et par pack, format spécifique."""

    def setUp(self):
        super().setUp()
        self.sucre = Article.objects.create(type_article="MATIERE_PREMIERE", unite_mesure="KG")
        self.preforme = Article.objects.create(type_article="EMBALLAGE", unite_mesure="UNITE")
        self.film = Article.objects.create(type_article="EMBALLAGE", unite_mesure="KG")
        self.jus = self.nouveau_pf(famille="Jus", format="1 L", unite="Pack de 6", parfum="Orange")
        self.jus15 = self.nouveau_pf(famille="Jus", format="1,5 L", unite="Pack de 6", parfum="Orange")
        self.preforme15 = Article.objects.create(type_article="EMBALLAGE", unite_mesure="UNITE")
        self.fiche = FicheTechnique.objects.create(article=self.jus, version=1, cree_par=self.admin)
        self.fiche.quantite_reference = 1000
        self.fiche.unite_reference = "L"
        self.fiche.save()
        self.fiche.formats_associes.add(self.jus15)
        CompositionFicheTechnique.objects.create(fiche_technique=self.fiche, matiere=self.sucre, quantite_necessaire=100, prix_unitaire=500)
        CompositionFicheTechnique.objects.create(
            fiche_technique=self.fiche, matiere=self.preforme, quantite_necessaire=1, base_calcul="UNITE", article_format=self.jus,
        )
        CompositionFicheTechnique.objects.create(
            fiche_technique=self.fiche, matiere=self.preforme15, quantite_necessaire=1, base_calcul="UNITE", article_format=self.jus15,
        )
        CompositionFicheTechnique.objects.create(
            fiche_technique=self.fiche, matiere=self.film, quantite_necessaire=Decimal("0.05"), base_calcul="PACK",
            perte_theorique_pct=2,
        )
        self.fiche.valider(self.admin)

    def test_besoins_selon_les_bases_de_calcul(self):
        of = OrdreFabrication.objects.create(article=self.jus, quantite_a_produire=6000, responsable=self.admin)
        besoins = {b.matiere_id: b.quantite_theorique for b in of.besoins_matieres.all()}
        self.assertEqual(besoins[self.sucre.id], Decimal("600"))            # 6 000 L x 100 kg / 1 000 L
        self.assertEqual(besoins[self.preforme.id], Decimal("6000"))        # 1 par bouteille
        self.assertEqual(besoins[self.film.id], Decimal("51"))              # 1 000 packs x 0,05 kg + 2 %
        self.assertNotIn(self.preforme15.id, besoins)                       # emballage d'un autre format

    def test_recette_partagee_par_un_autre_format(self):
        of = OrdreFabrication.objects.create(article=self.jus15, quantite_a_produire=600, responsable=self.admin)
        self.assertEqual(of.fiche_technique, self.fiche)
        besoins = {b.matiere_id: b.quantite_theorique for b in of.besoins_matieres.all()}
        self.assertEqual(besoins[self.sucre.id], Decimal("90"))             # 600 x 1,5 L = 900 L
        self.assertIn(self.preforme15.id, besoins)
        self.assertNotIn(self.preforme.id, besoins)

    def test_recette_en_test_figee(self):
        fiche = FicheTechnique.objects.create(article=self.jus, version=2, cree_par=self.admin)
        CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=self.sucre, quantite_necessaire=1)
        self.assertEqual(self.api.post(f"/api/referentiel/fiches-techniques/{fiche.id}/mettre_en_test/").status_code, 200)
        r = self.assert_refus(self.api.post("/api/referentiel/compositions/", {
            "fiche_technique": fiche.id, "matiere": self.film.id, "quantite_necessaire": 1, "prix_unitaire": 0,
        }, format="json"))
        self.assertIn("brouillon", str(r.data))

    def test_conversion_centralisee(self):
        ConversionUnite.objects.create(article=self.sucre, unite_source="SAC", facteur=25, unite_cible="KG")
        self.assertEqual(self.sucre.convertir(2, "SAC", "G"), Decimal("50000"))
        r = self.api.get("/api/referentiel/conversions/convertir/", {"quantite": 3, "de": "SAC", "vers": "KG", "article": self.film.id})
        self.assertEqual(r.status_code, 400)   # conversion propre au sucre : pas pour le film


class LotsMatieresTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.magasin = depot_par_defaut("Magasin principal")
        self.entree_stock(self.matiere, 30)
        aujourd_hui = timezone.localdate()
        self.lot_tardif = LotMatiere.objects.create(article=self.matiere, depot=self.magasin, date_reception=aujourd_hui,
                                                    date_peremption=aujourd_hui + timedelta(days=60), quantite_initiale=10)
        self.lot_proche = LotMatiere.objects.create(article=self.matiere, depot=self.magasin, date_reception=aujourd_hui,
                                                    date_peremption=aujourd_hui + timedelta(days=5), quantite_initiale=10)
        self.of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=5, responsable=self.admin)

    def test_on_ne_lote_pas_plus_que_le_stock(self):
        r = self.assert_refus(self.api.post("/api/stocks/lots-matieres/", {
            "article": self.matiere.id, "depot": self.magasin.id, "date_reception": str(date.today()), "quantite_initiale": 11,
        }, format="json"))
        self.assertIn("quantite_initiale", r.data)

    def test_sortie_consomme_la_dlc_la_plus_proche_puis_retour(self):
        SortieMatiere.objects.create(ordre_fabrication=self.of, matiere=self.matiere, quantite_sortie=12)
        self.lot_proche.refresh_from_db()
        self.lot_tardif.refresh_from_db()
        self.assertEqual(self.lot_proche.statut, "EPUISE")
        self.assertEqual(self.lot_tardif.quantite_restante, Decimal("8"))
        RetourMatiere.objects.create(ordre_fabrication=self.of, matiere=self.matiere, quantite_retournee=3)
        self.lot_tardif.refresh_from_db()
        self.assertEqual(self.lot_tardif.quantite_restante, Decimal("10"))
        lots = self.api.get(f"/api/production/ordres-fabrication/{self.of.id}/lots_consommes/").data
        self.assertEqual({l["lot_numero"] for l in lots}, {self.lot_proche.numero, self.lot_tardif.numero})

    def test_lot_bloque_indisponible(self):
        self.lot_proche.changer_statut("BLOQUE")
        stock = StockArticle.objects.get(article=self.matiere, depot=self.magasin)
        self.assertEqual(stock.quantite_disponible, Decimal("20"))
        self.assert_refus(self.api.post("/api/production/sorties-matieres/", {
            "ordre_fabrication": self.of.id, "matiere": self.matiere.id, "quantite_sortie": 25,
        }, format="json"))
        self.assertFalse(ConsommationLotMatiere.objects.exists())

    def test_tracabilite_du_lot_produit_fini(self):
        SortieMatiere.objects.create(ordre_fabrication=self.of, matiere=self.matiere, quantite_sortie=5)
        lot_pf = Lot.objects.create(article=self.produit, ordre_fabrication=self.of, quantite=5, date_production=date.today())
        trace = self.api.get(f"/api/qualite/lots/{lot_pf.id}/tracabilite/").data
        self.assertEqual(trace["of"]["numero"], self.of.numero)
        self.assertEqual(trace["matieres"][0]["lot"], self.lot_proche.numero)
        aval = self.api.get(f"/api/stocks/lots-matieres/{self.lot_proche.id}/tracabilite/").data
        self.assertEqual(aval["ordres_fabrication"][0]["lots_produits_finis"][0]["lot"], lot_pf.numero_lot)


class TransfertTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.source = depot_par_defaut("Dépôt produits finis")
        self.depot_nord = Depot.objects.create(nom="Dépôt Nord", type_lieu="DEPOT_EXTERIEUR")
        self.entree_stock(self.produit, 50, depot="Dépôt produits finis")
        self.transfert = TransfertStock.objects.create(depot_source=self.source, depot_destination=self.depot_nord, cree_par=self.admin)

    def test_transfert_deplace_vraiment_le_stock(self):
        LigneTransfert.objects.create(transfert=self.transfert, article=self.produit, quantite=20)
        self.assertEqual(self.api.post(f"/api/stocks/transferts/{self.transfert.id}/expedier/").status_code, 200)
        self.assertEqual(StockArticle.objects.get(article=self.produit, depot=self.source).quantite_physique, 30)
        self.assertFalse(StockArticle.objects.filter(article=self.produit, depot=self.depot_nord, quantite_physique__gt=0).exists())
        self.assertEqual(self.api.post(f"/api/stocks/transferts/{self.transfert.id}/receptionner/").status_code, 200)
        self.assertEqual(StockArticle.objects.get(article=self.produit, depot=self.depot_nord).quantite_physique, 20)
        self.assertEqual(self.depot_nord.code[:4], "DEP-")

    def test_expedition_tout_ou_rien(self):
        LigneTransfert.objects.create(transfert=self.transfert, article=self.produit, quantite=20)
        LigneTransfert.objects.create(transfert=self.transfert, article=self.matiere, quantite=5)   # pas de stock
        self.assert_refus(self.api.post(f"/api/stocks/transferts/{self.transfert.id}/expedier/"))
        self.transfert.refresh_from_db()
        self.assertEqual(self.transfert.statut, "BROUILLON")
        self.assertEqual(StockArticle.objects.get(article=self.produit, depot=self.source).quantite_physique, 50)


class QualiteModuleTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.ph = ParametreQualite.objects.get(libelle="pH")
        self.instrument = Instrument.objects.create(
            designation="pH-mètre", periodicite_etalonnage_jours=30, date_dernier_etalonnage=timezone.localdate(),
        )
        self.point = PointControle.objects.create(
            designation="pH eau traitée", parametre=self.ph, activite=Activite.objects.get(code="EAU"),
            etape=EtapeStandard.objects.get(code="TRAITEMENT"), valeur_min=Decimal("6.5"), valeur_max=Decimal("8.5"),
            bloquant=True, declencheur="CHAQUE_OF", instrument=self.instrument, statut="ACTIF",
        )
        self.entree_stock(self.matiere, 20)
        self.of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        for _ in range(4):   # brouillon -> en production
            self.of.passer_statut_suivant()

    def avancer_jusqu_au_controle(self):
        self.of.passer_statut_suivant()
        self.of.passer_statut_suivant()

    def test_activation_sans_critere_refusee(self):
        r = self.assert_refus(self.api.post("/api/qualite/plan-controle/", {
            "designation": "Brix", "parametre": ParametreQualite.objects.get(libelle="Brix / taux de sucre").id,
            "activite": Activite.objects.get(code="JUS").id, "declencheur": "CHAQUE_LOT", "statut": "ACTIF",
        }, format="json"))
        self.assertIn("critères", str(r.data))

    def test_controle_genere_et_conformite_calculee(self):
        controle = ResultatControle.objects.get(point=self.point, ordre_fabrication=self.of)
        self.assertEqual(controle.statut, "A_REALISER")
        self.assertEqual(controle.etape.code, "TRAITEMENT")
        r = self.api.post(f"/api/qualite/controles-realises/{controle.id}/enregistrer/", {"valeur": "7.2"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "CONFORME")
        self.avancer_jusqu_au_controle()
        self.of.passer_statut_suivant()
        self.assertEqual(self.of.statut, "CLOTURE")

    def test_non_conformite_bloquante_jusqu_a_la_reprise(self):
        controle = ResultatControle.objects.get(point=self.point, ordre_fabrication=self.of)
        r = self.api.post(f"/api/qualite/controles-realises/{controle.id}/enregistrer/", {"valeur": "9.1"}, format="json")
        self.assertEqual(r.data["statut"], "NON_CONFORME")
        nc = NonConformite.objects.get(resultat=controle)
        self.assertTrue(nc.bloquante)
        self.avancer_jusqu_au_controle()
        with self.assertRaisesMessage(ValueError, "non-conformité"):
            self.of.passer_statut_suivant()
        refus = self.assert_refus(self.api.post(f"/api/qualite/non-conformites/{nc.id}/cloturer/", {
            "decision": "LIBERATION", "action_corrective": "Remplacement de la cartouche",
        }, format="json"))
        self.assertIn("reprise", str(refus.data))
        reprise = self.api.post(f"/api/qualite/controles-realises/{controle.id}/reprise/").data
        self.api.post(f"/api/qualite/controles-realises/{reprise['id']}/enregistrer/", {"valeur": "7.0"}, format="json")
        ok = self.api.post(f"/api/qualite/non-conformites/{nc.id}/cloturer/", {
            "decision": "LIBERATION", "action_corrective": "Remplacement de la cartouche",
        }, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.of.passer_statut_suivant()
        self.assertEqual(self.of.statut, "CLOTURE")

    def test_instrument_non_etalonne_refuse(self):
        Instrument.objects.filter(pk=self.instrument.pk).update(date_dernier_etalonnage=timezone.localdate() - timedelta(days=60))
        controle = ResultatControle.objects.get(point=self.point, ordre_fabrication=self.of)
        r = self.assert_refus(self.api.post(f"/api/qualite/controles-realises/{controle.id}/enregistrer/", {"valeur": "7"}, format="json"))
        self.assertIn("étalonné", str(r.data))
        controle.refresh_from_db()
        self.assertEqual(controle.statut, "A_REALISER")

    def test_lot_non_libere_si_controle_bloquant_en_attente(self):
        lot = Lot.objects.create(article=self.produit, ordre_fabrication=self.of, quantite=10, date_production=date.today())
        r = self.assert_refus(self.api.post("/api/qualite/controles/", {"lot": lot.id, "resultat": "CONFORME"}, format="json"))
        self.assertIn("bloquant", str(r.data))

    def test_filtres_et_indicateurs(self):
        controle = ResultatControle.objects.get(point=self.point, ordre_fabrication=self.of)
        self.api.post(f"/api/qualite/controles-realises/{controle.id}/enregistrer/", {"valeur": "9"}, format="json")
        liste = self.api.get("/api/qualite/controles-realises/", {"bloquant": "true", "statut": "NON_CONFORME",
                                                                    "activite": Activite.objects.get(code="EAU").id})
        self.assertEqual(liste.data["count"] if "count" in liste.data else len(liste.data), 1)
        kpi = self.api.get("/api/qualite/indicateurs/").data
        self.assertEqual(kpi["taux_conformite"], 0.0)
        self.assertEqual(kpi["non_conformites"]["bloquantes_ouvertes"], 1)


class CoutsCascadeTests(BaseValidation):
    """Exemple du document : forage commun réparti au volume d'eau, puis aux OF, puis à l'unité."""

    def setUp(self):
        super().setUp()
        self.periode = timezone.localdate().strftime("%Y-%m")
        self.jus = self.nouveau_pf(famille="Jus", format="1 L", unite="Pack de 6", parfum="Orange")
        fiche = FicheTechnique.objects.create(article=self.jus, version=1, cree_par=self.admin)
        CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=self.matiere, quantite_necessaire=1)
        fiche.valider(self.admin)
        self.of_eau = self.of_cloture(self.produit, 6000, litres=6000)
        self.of_jus = self.of_cloture(self.jus, 2000, litres=2000)
        self.forage = NatureCout.objects.get(libelle="Électricité des pompes de forage")

    def of_cloture(self, article, quantite, litres):
        of = OrdreFabrication.objects.create(article=article, quantite_a_produire=quantite, responsable=self.admin)
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="EN_PRODUCTION")
        of.refresh_from_db()
        SuiviEau.objects.create(
            ordre_fabrication=of, volume_capte_l=litres, volume_obtenu_traitement_l=litres,
            volume_envoye_embouteillage_l=litres, bouteilles_produites=quantite, bouteilles_conformes=quantite,
        )
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="CLOTURE", date_fin=timezone.now())
        of.refresh_from_db()
        return of

    def test_cascade_forage_jusqu_a_l_unite(self):
        charge = Charge.objects.create(nature=self.forage, periode=self.periode, montant=Decimal("10000"), source="Facture SBEE 42")
        resultat = cascade.calculer_periode(self.periode)
        self.assertEqual(resultat["anomalies_double_compte"], [])
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "REPARTIE")
        eau = RepartitionCout.objects.get(charge=charge, niveau="ACTIVITE", activite__code="EAU")
        self.assertEqual(eau.montant, Decimal("7500.00"))                  # 6 m³ sur 8
        self.assertEqual(eau.valeur_cle_part, Decimal("6"))
        produit = RepartitionCout.objects.get(charge=charge, niveau="PRODUIT", ordre_fabrication=self.of_eau)
        self.assertEqual(produit.cout_par_unite.quantize(Decimal("0.0001")), Decimal("1.2500"))   # 7 500 / 6 000
        self.assertEqual(produit.cout_par_pack.quantize(Decimal("0.01")), Decimal("10.00"))     # pack de 8
        self.of_eau.cout_reel.refresh_from_db()
        self.assertEqual(self.of_eau.cout_reel.cout_charges_reparties, Decimal("7500.00"))

    def test_charge_sans_cle_reste_non_repartie(self):
        nature = NatureCout.objects.get(libelle="Électricité soufflage")   # heures machine : aucune saisie
        charge = Charge.objects.create(nature=nature, periode=self.periode, montant=500)
        cascade.calculer_periode(self.periode)
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "NON_REPARTIE")
        self.assertFalse(charge.repartitions.exists())

    def test_cle_estimee_jamais_presentee_comme_mesure(self):
        nature = NatureCout.objects.create(libelle="Énergie soufflage (kWh)", etape=EtapeStandard.objects.get(code="SOUFFLAGE"),
                                           inducteur="KWH", traitement="INDIRECT")
        OrdreFabrication.objects.filter(pk=self.of_eau.pk).update(statut="EN_PRODUCTION")
        EtapeProduction.objects.create(ordre_fabrication=OrdreFabrication.objects.get(pk=self.of_eau.pk), etape="SOUFFLAGE",
                                       agent=self.admin, energie_kwh=100, energie_mesuree=False)
        OrdreFabrication.objects.filter(pk=self.of_eau.pk).update(statut="CLOTURE")
        Charge.objects.create(nature=nature, periode=self.periode, montant=300)
        cascade.calculer_periode(self.periode)
        ligne = RepartitionCout.objects.get(niveau="OF", ordre_fabrication=self.of_eau, charge__nature=nature)
        self.assertEqual(ligne.statut, "ESTIME")

    def test_charge_directe_d_une_cuve_dediee(self):
        Charge.objects.create(nature=NatureCout.objects.get(libelle="Maintenance cuves"), periode=self.periode,
                              montant=800, activite=Activite.objects.get(code="JUS"))
        cascade.calculer_periode(self.periode)
        ligne = RepartitionCout.objects.get(niveau="OF", ordre_fabrication=self.of_jus)
        self.assertEqual(ligne.montant, Decimal("800.00"))
        self.assertFalse(RepartitionCout.objects.filter(ordre_fabrication=self.of_eau).exists())

    def test_api_cout_revient_et_eau_traitee(self):
        Charge.objects.create(nature=self.forage, periode=self.periode, montant=Decimal("8000"))
        self.assertEqual(self.api.post("/api/couts/cascade/calculer/", {"periode": self.periode}, format="json").status_code, 200)
        revient = self.api.get("/api/couts/cascade/cout-revient/", {"periode": self.periode}).data
        self.assertEqual(len(revient["ofs"]), 2)
        eau = {ligne["activite"]: ligne for ligne in self.api.get("/api/couts/cascade/eau-traitee/", {"periode": self.periode}).data}
        self.assertEqual(eau["EAU"]["cout_par_m3"], Decimal("1000"))      # 6 000 pour 6 m³
        self.assertTrue(self.api.get("/api/couts/cascade/controle/", {"periode": self.periode}).data["conforme"])
