"""
Tests des ordres de fabrication selon les réponses du client
(questionnaire Q27 à Q32) : plusieurs formats par OF, réservation du
stock au lancement, ligne au lancement, planning par ligne et capacités.

Lancer : python manage.py test apps.industriel.tests_of
"""

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.core.tests import BaseValidation
from apps.couts.models import CoutReel
from apps.industriel.models import Activite, Ligne, Usine
from apps.production.models import FormatOF, OrdreFabrication, ParametreProduction, SortieMatiere
from apps.qualite.models import Lot
from apps.referentiel.models import CompositionFicheTechnique, FicheTechnique
from apps.stocks.models import StockArticle, depot_par_defaut


class MultiFormatTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.grand = self.nouveau_pf(format="150 cl", unite="Pack de 6")   # EAU150P6
        fiche = FicheTechnique.objects.create(article=self.grand, version=1, cree_par=self.admin)
        CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=self.matiere, quantite_necessaire=3, prix_unitaire=10)
        fiche.valider(self.admin)
        self.of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)

    def test_besoins_de_tous_les_formats(self):
        r = self.api.post("/api/production/formats-of/", {"ordre_fabrication": self.of.id, "article": self.grand.id, "quantite_a_produire": 5}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.of.besoins_matieres.get().quantite_theorique, Decimal(35))   # 10 x 2 + 5 x 3
        self.assert_refus(self.api.post("/api/production/formats-of/", {"ordre_fabrication": self.of.id, "article": self.produit.id, "quantite_a_produire": 1}, format="json"))
        jus = self.nouveau_pf(famille="Jus", parfum="Orange")
        self.assert_refus(self.api.post("/api/production/formats-of/", {"ordre_fabrication": self.of.id, "article": jus.id, "quantite_a_produire": 1}, format="json"))

    def test_lots_et_cout_par_format(self):
        FormatOF.objects.create(ordre_fabrication=self.of, article=self.grand, quantite_a_produire=5)
        OrdreFabrication.objects.filter(pk=self.of.pk).update(statut="EN_CONTROLE")
        self.of.refresh_from_db()
        lot_petit = Lot.objects.create(article=self.produit, ordre_fabrication=self.of, quantite=10, date_production=date.today())
        lot_grand = Lot.objects.create(article=self.grand, ordre_fabrication=self.of, quantite=5, date_production=date.today())
        cout = CoutReel.objects.create(ordre_fabrication=self.of, cout_matiere_total=Decimal("350"))
        lignes = {l["article"].code: l for l in cout.ventilation_par_format()}
        # matières ventilées sur la valeur théorique : 10 x 2 x 0 (MP1 sans prix sur la fiche du petit format)
        # -> repli sur les litres produits : 7 L (petit) et 7,5 L (grand)
        self.assertEqual(lignes[self.produit.code]["cout"] + lignes[self.grand.code]["cout"], Decimal("350"))
        self.assertEqual(lignes[self.grand.code]["cout"], Decimal("181.03"))
        for lot in (lot_petit, lot_grand):
            Lot.objects.filter(pk=lot.pk).update(statut="CONFORME")
            lot.refresh_from_db()
            lot.liberer(self.admin)
        entree_grand = StockArticle.objects.get(article=self.grand, depot=depot_par_defaut("Dépôt produits finis"))
        self.assertEqual(entree_grand.quantite_physique, 5)


class ReservationTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.entree_stock(self.matiere, 30)   # un OF de 10 a besoin de 20
        self.premier = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        self.second = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        self.magasin = depot_par_defaut("Magasin principal")

    def stock(self):
        return StockArticle.objects.get(article=self.matiere, depot=self.magasin)

    def test_reservation_bloque_le_second_of(self):
        self.premier.passer_statut_suivant()
        self.assertEqual(self.stock().quantite_reservee, 20)
        with self.assertRaisesMessage(ValueError, "stock insuffisant"):
            self.second.passer_statut_suivant()
        verification = self.api.get(f"/api/production/ordres-fabrication/{self.second.id}/verifier_stock/").data
        self.assertEqual(verification["manques"][0]["manquant"], Decimal(10))

    def test_sortie_consomme_la_reservation_puis_annulation_libere(self):
        self.premier.passer_statut_suivant()
        SortieMatiere.objects.create(ordre_fabrication=self.premier, matiere=self.matiere, quantite_sortie=15)
        stock = self.stock()
        self.assertEqual((stock.quantite_physique, stock.quantite_reservee), (Decimal(15), Decimal(5)))
        self.premier.annuler("Panne")
        self.assertEqual(self.stock().quantite_reservee, 0)
        with self.assertRaisesMessage(ValueError, "stock insuffisant"):   # 15 en stock pour 20 nécessaires
            self.second.passer_statut_suivant()


class LigneEtPlanningTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.entree_stock(self.matiere, 100)
        eau, usine = Activite.objects.get(code="EAU"), Usine.objects.get(code="US-EAU")
        self.ligne1 = Ligne.objects.create(designation="Ligne Eau 1", usine=usine, activite=eau, cadence_nominale=5, unite_cadence="bouteilles/h")
        self.of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)

    def test_ligne_unique_retenue_au_lancement_sinon_a_choisir(self):
        self.of.passer_statut_suivant()
        self.assertEqual(self.of.ligne, self.ligne1)
        Ligne.objects.create(designation="Ligne Eau 2", usine=self.ligne1.usine, activite=self.ligne1.activite)
        autre = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=5, responsable=self.admin)
        with self.assertRaisesMessage(ValueError, "Choisissez la ligne"):
            autre.passer_statut_suivant()

    def test_planning_sans_chevauchement_et_fin_calculee(self):
        debut = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)
        r = self.api.patch(f"/api/production/ordres-fabrication/{self.of.id}/", {"ligne": self.ligne1.id, "date_debut_prevue": debut.isoformat()}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.of.refresh_from_db()
        self.assertEqual(self.of.date_fin_prevue - self.of.date_debut_prevue, timedelta(hours=2))   # 10 bouteilles à 5/h
        autre = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=40, responsable=self.admin)
        refus = self.assert_refus(self.api.patch(f"/api/production/ordres-fabrication/{autre.id}/", {
            "ligne": self.ligne1.id, "date_debut_prevue": (debut + timedelta(hours=1)).isoformat(),
        }, format="json"))
        self.assertIn(self.of.numero, str(refus.data))
        self.api.patch(f"/api/production/ordres-fabrication/{autre.id}/", {
            "ligne": self.ligne1.id, "date_debut_prevue": (debut + timedelta(hours=2)).isoformat(),
        }, format="json")   # 40 / 5 = 8 h : 10 h dans la journée > 8 h de capacité
        planning = self.api.get("/api/production/planning/", {"du": debut.date().isoformat(), "au": debut.date().isoformat()}).data
        jour = planning["lignes"][0]["jours"][0]
        self.assertEqual(jour["heures_planifiees"], Decimal("10.00"))
        self.assertTrue(jour["surcharge"])
        ParametreProduction.objects.update_or_create(pk=1, defaults={"heures_ouvrees_par_jour": 16})
        self.assertFalse(self.api.get("/api/production/planning/", {"du": debut.date().isoformat(), "au": debut.date().isoformat()}).data["lignes"][0]["jours"][0]["surcharge"])
