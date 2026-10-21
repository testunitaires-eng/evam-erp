"""
Tests du socle industriel, des recettes, des lots matières, du module
Contrôle qualité et des coûts en cascade (documents EVAM de paramétrage,
de circuit, de contrôle qualité et de calcul des coûts).

Lancer : python manage.py test apps.industriel
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.tests import BaseValidation
from apps.commercial.models import Facture
from apps.couts import cascade
from apps.couts.models import Charge, NatureCout, RepartitionCout, ValeurCle, VolumeEauSite
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
        forage = NatureCout.objects.get(libelle="Électricité des pompes de forage")
        self.assertEqual((forage.inducteur, forage.inducteur_of), ("VOLUME_EAU_BRUTE_M3", "QUANTITE_PRODUITE"))

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


class QualiteBase(BaseValidation):
    """Mise en place commune : un contrôle pH bloquant au plan, un OF Eau en production."""

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


class QualiteModuleTests(QualiteBase):

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


class CoutsBase(BaseValidation):
    """Deux OF clôturés (Eau 6 000 bouteilles de 70 cl, Jus 2 000 L) et la nature « forage »."""

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
        self.us_eau, self.us_jy = Usine.objects.get(code="US-EAU"), Usine.objects.get(code="US-JY")
        self.eau_act = Activite.objects.get(code="EAU")
        self.jus_act, self.yaourt_act = Activite.objects.get(code="JUS"), Activite.objects.get(code="YAOURT")

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

    def compteurs(self, eau, jus, yaourt, estime=()):
        """Relevés des compteurs d'eau brute captée (m³) par activité."""
        for usine, activite, volume in ((self.us_eau, self.eau_act, eau), (self.us_jy, self.jus_act, jus), (self.us_jy, self.yaourt_act, yaourt)):
            estimation = activite.code in estime
            VolumeEauSite.objects.create(
                periode=self.periode, usine=usine, activite=activite, volume_m3=volume, source=f"Compteur {activite.code}",
                statut_donnee="ESTIME" if estimation else "REEL", justification="Compteur en panne : moyenne des 3 derniers mois." if estimation else "",
            )

    def repartition(self, charge, niveau, **filtres):
        return RepartitionCout.objects.get(charge=charge, niveau=niveau, **filtres)


class CoutsCascadeTests(CoutsBase):
    """Exemple du document : forage commun réparti à l'eau brute captée, puis aux OF selon la production, puis à l'unité."""

    def test_cascade_forage_jusqu_a_l_unite(self):
        self.compteurs(eau=6, jus=2, yaourt=0)
        charge = Charge.objects.create(nature=self.forage, periode=self.periode, montant=Decimal("10000"), source="Facture SBEE 42")
        resultat = cascade.calculer_periode(self.periode)
        self.assertEqual(resultat["anomalies_double_compte"], [])
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "REPARTIE")
        site_eau = self.repartition(charge, "SITE", usine=self.us_eau)
        self.assertEqual(site_eau.montant, Decimal("7500.00"))             # 6 m³ d'eau brute sur 8
        self.assertEqual(site_eau.valeur_cle_part, Decimal("6"))
        self.assertEqual(self.repartition(charge, "ACTIVITE", activite=self.jus_act).montant, Decimal("2500.00"))
        ligne_of = self.repartition(charge, "OF", ordre_fabrication=self.of_eau)
        self.assertEqual(ligne_of.inducteur, "QUANTITE_PRODUITE")
        self.assertEqual(ligne_of.unite_cle, "L")
        produit = self.repartition(charge, "PRODUIT", ordre_fabrication=self.of_eau)
        self.assertEqual(produit.cout_par_unite.quantize(Decimal("0.0001")), Decimal("1.2500"))   # 7 500 / 6 000
        self.assertEqual(produit.cout_par_pack.quantize(Decimal("0.01")), Decimal("10.00"))     # pack de 8
        self.of_eau.cout_reel.refresh_from_db()
        self.assertEqual(self.of_eau.cout_reel.cout_charges_reparties, Decimal("7500.00"))

    def test_forage_sans_releve_des_compteurs(self):
        charge = Charge.objects.create(nature=self.forage, periode=self.periode, montant=Decimal("10000"))
        cascade.calculer_periode(self.periode)
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "NON_REPARTIE")
        self.assertIn("compteurs d'eau brute", charge.motif_non_repartition)

    def test_charge_sans_cle_reste_non_repartie(self):
        nature = NatureCout.objects.get(libelle="Maintenance souffleuse")   # heures machine : aucune saisie
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
                              montant=800, activite=self.jus_act)
        cascade.calculer_periode(self.periode)
        ligne = RepartitionCout.objects.get(niveau="OF", ordre_fabrication=self.of_jus)
        self.assertEqual(ligne.montant, Decimal("800.00"))
        self.assertFalse(RepartitionCout.objects.filter(ordre_fabrication=self.of_eau).exists())

    def test_traitement_de_l_eau_affecte_a_l_eau(self):
        charge = Charge.objects.create(nature=NatureCout.objects.get(libelle="Électricité traitement de l'eau"),
                                       periode=self.periode, montant=900)
        self.assertEqual(charge.activite, self.eau_act)
        cascade.calculer_periode(self.periode)
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=self.of_eau).montant, Decimal("900.00"))
        self.assertFalse(RepartitionCout.objects.filter(charge=charge, ordre_fabrication=self.of_jus).exists())

    def test_ofs_d_une_activite_repartis_au_litre(self):
        of_eau_2 = self.of_cloture(self.produit, 3000, litres=3000)        # 2 100 L contre 4 200 L
        charge = Charge.objects.create(nature=NatureCout.objects.get(libelle="Électricité remplissage"),
                                       periode=self.periode, montant=Decimal("900"), activite=self.eau_act)
        cascade.calculer_periode(self.periode)
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=self.of_eau).montant, Decimal("600.00"))
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=of_eau_2).montant, Decimal("300.00"))

    def test_api_cout_revient_et_eau_traitee(self):
        self.compteurs(eau=6, jus=2, yaourt=0)
        Charge.objects.create(nature=self.forage, periode=self.periode, montant=Decimal("8000"))
        self.assertEqual(self.api.post("/api/couts/cascade/calculer/", {"periode": self.periode}, format="json").status_code, 200)
        revient = self.api.get("/api/couts/cascade/cout-revient/", {"periode": self.periode}).data
        self.assertEqual(len(revient["ofs"]), 2)
        eau = {ligne["activite"]: ligne for ligne in self.api.get("/api/couts/cascade/eau-traitee/", {"periode": self.periode}).data}
        self.assertEqual(eau["EAU"]["cout_par_m3"], Decimal("1000"))      # 6 000 pour 6 m³
        self.assertTrue(self.api.get("/api/couts/cascade/controle/", {"periode": self.periode}).data["conforme"])

    def test_commercialisation_dans_le_cout_de_revient(self):
        commande = self.commande(lignes=((10, 100),), statut="VALIDEE")   # 10 bouteilles d'eau vendues
        facture = Facture.objects.create(commande=commande)
        self.assertEqual(self.api.post(f"/api/commercial/factures/{facture.id}/generer_lignes/").status_code, 200)
        charge = Charge.objects.create(nature=NatureCout.objects.get(libelle__startswith="Points de vente et caisses"),
                                       periode=self.periode, montant=Decimal("500"))
        cascade.calculer_periode(self.periode)
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "REPARTIE")
        ligne = self.repartition(charge, "ARTICLE", article=self.produit)
        self.assertEqual(ligne.cout_par_unite, Decimal("50"))             # 500 / 10 unités vendues
        produit = next(p for p in cascade.cout_revient(self.periode)["produits"] if p["article"] == self.produit.code)
        self.assertEqual(produit["commercialisation"], Decimal("500.00"))
        self.assertEqual(produit["cout_revient_complet"], produit["production"] + Decimal("500.00"))
        self.assertEqual(produit["commercialisation_par_unite"], Decimal("50"))


class CoutsSitesTests(CoutsBase):
    """Schémas client : niveau site, yaourt en kg, clés de site, facture découpée (montants ou kWh par étape), synthèse par site."""

    def setUp(self):
        super().setUp()
        self.yaourt = self.nouveau_pf(famille="Yaourt", format="125 g", unite="Pack de 8", parfum="Fraise")
        fiche = FicheTechnique.objects.create(article=self.yaourt, version=1, cree_par=self.admin)
        CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=self.matiere, quantite_necessaire=1)
        fiche.valider(self.admin)
        self.of_yaourt = self.of_cloture(self.yaourt, 8000, litres=1000)   # 8 000 pots de 125 g = 1 000 kg

    def test_charge_d_un_site_partagee_en_litres_equivalents(self):
        nature = NatureCout.objects.get(libelle__startswith="Électricité utilités du site")
        charge = Charge.objects.create(nature=nature, periode=self.periode, montant=Decimal("900"), usine=self.us_jy)
        resultat = cascade.calculer_periode(self.periode)
        self.assertEqual(resultat["anomalies_double_compte"], [])
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "REPARTIE")
        self.assertEqual(self.repartition(charge, "SITE").montant, Decimal("900.00"))
        self.assertEqual(self.repartition(charge, "ACTIVITE", activite=self.jus_act).montant, Decimal("600.00"))     # 2 000 L / 1 000 kg (1 kg = 1 L)
        self.assertEqual(self.repartition(charge, "ACTIVITE", activite=self.yaourt_act).montant, Decimal("300.00"))
        ligne_yaourt = self.repartition(charge, "OF", ordre_fabrication=self.of_yaourt)
        self.assertEqual((ligne_yaourt.unite_cle, ligne_yaourt.valeur_cle_part), ("kg", Decimal("1000")))
        self.assertFalse(RepartitionCout.objects.filter(charge=charge, ordre_fabrication=self.of_eau).exists())
        # Coefficient de l'activité (kg -> L) paramétrable.
        Activite.objects.filter(pk=self.yaourt_act.pk).update(litres_equivalents_par_unite=Decimal("0.5"))
        cascade.calculer_periode(self.periode)
        self.assertEqual(self.repartition(charge, "ACTIVITE", activite=self.jus_act).montant, Decimal("720.00"))     # 2 000 contre 500

    def test_charge_de_site_refuse_une_activite_d_un_autre_site(self):
        nature = NatureCout.objects.get(libelle__startswith="Électricité utilités du site")
        with self.assertRaises(ValidationError):
            Charge.objects.create(nature=nature, periode=self.periode, montant=100, usine=self.us_jy, activite=self.eau_act)

    def test_forage_reparti_selon_les_compteurs_d_eau_brute(self):
        self.compteurs(eau=7, jus=2, yaourt=1, estime=("YAOURT",))
        charge = Charge.objects.create(nature=self.forage, periode=self.periode, montant=Decimal("10000"))
        resultat = cascade.calculer_periode(self.periode)
        self.assertEqual(resultat["anomalies_double_compte"], [])
        self.assertEqual(self.repartition(charge, "SITE", usine=self.us_eau).montant, Decimal("7000.00"))
        self.assertEqual(self.repartition(charge, "SITE", usine=self.us_jy).montant, Decimal("3000.00"))
        self.assertEqual(self.repartition(charge, "SITE", usine=self.us_jy).statut, "ESTIME")
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=self.of_eau).montant, Decimal("7000.00"))
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=self.of_jus).montant, Decimal("2000.00"))
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=self.of_yaourt).montant, Decimal("1000.00"))
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=self.of_yaourt).statut, "ESTIME")

        synthese = self.api.get("/api/couts/cascade/par-site/", {"periode": self.periode}).data
        sites = {site["usine"]: site for site in synthese["sites"]}
        self.assertEqual(sites["US-EAU"]["electricite"], Decimal("7000.00"))
        self.assertEqual(sites["US-JY"]["electricite"], Decimal("3000.00"))
        jus = next(a for a in sites["US-JY"]["activites"] if a["activite"] == "JUS")
        self.assertEqual(jus["descendu_aux_of"], Decimal("2000.00"))

    def test_compteur_d_eau_brute_manquant(self):
        VolumeEauSite.objects.create(periode=self.periode, usine=self.us_eau, activite=self.eau_act, volume_m3=7)
        charge = Charge.objects.create(nature=self.forage, periode=self.periode, montant=Decimal("10000"))
        cascade.calculer_periode(self.periode)
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "NON_REPARTIE")
        self.assertIn("US-JY", charge.motif_non_repartition)

    def test_infrastructures_de_production_dans_le_cout_des_of(self):
        debut = date(2000, 1, 1)
        ValeurCle.objects.create(inducteur="SURFACE_M2", usine=self.us_eau, valeur=600, date_debut=debut)
        ValeurCle.objects.create(inducteur="SURFACE_M2", usine=self.us_jy, activite=self.jus_act, valeur=250, date_debut=debut)
        ValeurCle.objects.create(inducteur="SURFACE_M2", usine=self.us_jy, activite=self.yaourt_act, valeur=150, date_debut=debut)
        nature = NatureCout.objects.get(libelle="Nettoyage des zones de production")
        charge = Charge.objects.create(nature=nature, periode=self.periode, montant=Decimal("1000"))
        resultat = cascade.calculer_periode(self.periode)
        self.assertEqual(resultat["anomalies_double_compte"], [])
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "REPARTIE")
        self.assertEqual(self.repartition(charge, "SITE", usine=self.us_jy).montant, Decimal("400.00"))
        self.assertEqual(self.repartition(charge, "ACTIVITE", activite=self.jus_act).montant, Decimal("250.00"))
        self.assertEqual(self.repartition(charge, "OF", ordre_fabrication=self.of_eau).montant, Decimal("600.00"))
        # Sans clé vers les OF, la charge s'arrête à l'activité.
        nature.inducteur_of = ""
        nature.save()
        cascade.calculer_periode(self.periode)
        charge.refresh_from_db()
        self.assertEqual(charge.statut_repartition, "PARTIELLE")
        self.assertFalse(charge.repartitions.filter(niveau="OF").exists())

    def test_chambre_froide_cle_au_choix(self):
        debut = date(2000, 1, 1)
        nature = NatureCout.objects.get(libelle="Électricité chambre froide de production")
        self.assertEqual(nature.inducteur, "VOLUME_OCCUPE_M3")
        for activite, volume, palettes in ((self.jus_act, 30, 4), (self.yaourt_act, 70, 4)):
            ValeurCle.objects.create(inducteur="VOLUME_OCCUPE_M3", usine=self.us_jy, activite=activite, valeur=volume, date_debut=debut)
            ValeurCle.objects.create(inducteur="EMPLACEMENTS_PALETTES", usine=self.us_jy, activite=activite, valeur=palettes, date_debut=debut)
        charge = Charge.objects.create(nature=nature, periode=self.periode, montant=Decimal("1000"), usine=self.us_jy)
        cascade.calculer_periode(self.periode)
        self.assertEqual(self.repartition(charge, "ACTIVITE", activite=self.yaourt_act).montant, Decimal("700.00"))
        nature.inducteur = "EMPLACEMENTS_PALETTES"
        nature.save()
        cascade.calculer_periode(self.periode)
        self.assertEqual(self.repartition(charge, "ACTIVITE", activite=self.yaourt_act).montant, Decimal("500.00"))

    def test_facture_d_electricite_decoupee(self):
        facture = self.api.post("/api/couts/factures/", {
            "reference": "SBEE 2026-0042", "periode": self.periode, "montant_total": "10000",
        }, format="json")
        self.assertEqual(facture.status_code, 201, facture.content)
        url = f"/api/couts/factures/{facture.data['id']}/ventiler/"
        utilites = NatureCout.objects.get(libelle__startswith="Électricité utilités du site")
        infra = NatureCout.objects.get(libelle__startswith="Électricité commune des infrastructures")
        parts = [
            {"nature": self.forage.pk, "montant": "6000"},
            {"nature": utilites.pk, "montant": "2500", "usine": self.us_jy.pk},
            {"nature": infra.pk, "montant": "1000"},
        ]
        refus = self.api.post(url, {"parts": parts}, format="json")
        self.assertEqual(refus.status_code, 400)
        self.assertFalse(Charge.objects.filter(facture_id=facture.data["id"]).exists())
        parts[2]["montant"] = "1500"
        r = self.api.post(url, {"parts": parts}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["est_ventilee"])
        self.assertEqual(len(r.data["parts"]), 3)
        self.assertEqual(cascade.calculer_periode(self.periode)["factures_incompletes"], [])
        Charge.objects.filter(facture_id=facture.data["id"], nature=infra).delete()
        incompletes = cascade.calculer_periode(self.periode)["factures_incompletes"]
        self.assertEqual(incompletes[0]["reste_a_ventiler"], Decimal("1500.00"))

    def test_facture_d_electricite_repartie_par_etape_aux_kwh(self):
        """Schéma client : 1 000 000 -> captage 200 000, traitement 300 000, soufflage 400 000, conditionnement 100 000."""
        facture = self.api.post("/api/couts/factures/", {
            "reference": "SBEE 2026-0043", "periode": self.periode, "montant_total": "1000000",
        }, format="json").data
        url = f"/api/couts/factures/{facture['id']}/repartir_par_etape/"
        self.assertEqual(self.api.post(url).status_code, 400)          # aucun relevé : ventilation manuelle
        for code, kwh in (("CAPTAGE", 200), ("TRAITEMENT", 300), ("SOUFFLAGE", 400), ("CONDITIONNEMENT", 100)):
            r = self.api.post("/api/couts/releves-electricite/", {
                "periode": self.periode, "etape": EtapeStandard.objects.get(code=code).pk, "kwh": kwh, "source": f"Compteur {code}",
            }, format="json")
            self.assertEqual(r.status_code, 201, r.content)
        r = self.api.post(url)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.data["est_ventilee"])
        parts = {part["nature_libelle"]: Decimal(part["montant"]) for part in r.data["parts"]}
        self.assertEqual(parts, {
            "Électricité des pompes de forage": Decimal("200000.00"),
            "Électricité traitement de l'eau": Decimal("300000.00"),
            "Électricité soufflage": Decimal("400000.00"),
            "Électricité plastification": Decimal("100000.00"),
        })
        traitement = Charge.objects.get(facture_id=facture["id"], nature__libelle="Électricité traitement de l'eau")
        self.assertEqual(traitement.activite, self.eau_act)               # affectation directe à l'Eau


class RecommandationsFrontendTests(QualiteBase):
    """Pièces jointes en base, endpoint blocages, lecture DAF, liste des OF sans requêtes en cascade."""

    def test_piece_jointe_conservee_en_base_et_protegee(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from rest_framework.test import APIClient
        from apps.comptes.models import Profil, Utilisateur
        controle = ResultatControle.objects.get(point=self.point, ordre_fabrication=self.of)
        r = self.api.post("/api/qualite/pieces-jointes/", {
            "resultat": controle.id, "description": "Bulletin d'analyse",
            "fichier": SimpleUploadedFile("bulletin.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["nom_fichier"], "bulletin.pdf")
        fichier = self.api.get(r.data["url"])
        self.assertEqual(fichier["Content-Type"], "application/pdf")
        self.assertEqual(fichier.content, b"%PDF-1.4 test")
        refus = self.api.post("/api/qualite/pieces-jointes/", {
            "resultat": controle.id, "fichier": SimpleUploadedFile("virus.exe", b"MZ", content_type="application/x-msdownload"),
        }, format="multipart")
        self.assertEqual(refus.status_code, 400)
        commercial = APIClient()
        commercial.force_authenticate(Utilisateur.objects.create_user("com", password="x", profil=Profil.COMMERCIAL))
        self.assertEqual(commercial.get(r.data["url"]).status_code, 403)

    def test_endpoint_blocages_qualite(self):
        r = self.api.get(f"/api/production/ordres-fabrication/{self.of.id}/blocages_qualite/")
        self.assertFalse(r.data["cloture_possible"])
        self.assertIn("bloquant", r.data["blocages"][0])
        controle = ResultatControle.objects.get(point=self.point, ordre_fabrication=self.of)
        self.api.post(f"/api/qualite/controles-realises/{controle.id}/enregistrer/", {"valeur": "7"}, format="json")
        self.assertTrue(self.api.get(f"/api/production/ordres-fabrication/{self.of.id}/blocages_qualite/").data["cloture_possible"])

    def test_daf_lit_les_of_et_les_tournees(self):
        from rest_framework.test import APIClient
        from apps.comptes.models import Profil, Utilisateur
        daf = APIClient()
        daf.force_authenticate(Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF))
        self.assertEqual(daf.get("/api/production/ordres-fabrication/").status_code, 200)
        self.assertEqual(daf.get("/api/distribution/tournees/").status_code, 200)
        self.assertEqual(daf.post("/api/production/ordres-fabrication/", {"article": self.produit.id, "quantite_a_produire": 1}, format="json").status_code, 403)

    def test_liste_des_of_en_nombre_de_requetes_constant(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def compter():
            with CaptureQueriesContext(connection) as requetes:
                self.assertEqual(self.api.get("/api/production/ordres-fabrication/").status_code, 200)
            return len(requetes)

        avant = compter()
        for _ in range(4):
            OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=5, responsable=self.admin)
        self.assertEqual(compter(), avant)
