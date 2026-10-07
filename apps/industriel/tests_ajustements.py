"""
Tests des ajustements demandés dans le questionnaire : unité de
consommation (Q7), machine combinée (Q13 / Q56), inducteur
d'amortissement par équipement (Q56), contrôle obligatoire (Q44),
bibliothèque de contrôles (Q43), données obligatoires par étape (Q33).

Lancer : python manage.py test apps.industriel.tests_ajustements
"""

from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.core.tests import BaseValidation
from apps.couts import cascade
from apps.couts.models import Charge
from apps.industriel.models import Activite, Equipement, EtapeStandard, Ligne, Poste, Usine
from apps.production.models import DonneeObligatoireEtape, EtapeProduction, OrdreFabrication
from apps.qualite.models import Instrument, Lot, ModeleControle, ParametreQualite, PointControle
from apps.referentiel.models import Article, CompositionFicheTechnique, FicheTechnique


class UniteConsommationTests(BaseValidation):
    def test_recette_en_grammes_besoin_en_kg(self):
        stabilisant = Article.objects.create(type_article="MATIERE_PREMIERE", unite_mesure="KG", unite_consommation="G")
        jus = self.nouveau_pf(famille="Jus", parfum="Mangue")
        fiche = FicheTechnique.objects.create(article=jus, version=1, cree_par=self.admin)
        ligne = CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=stabilisant, quantite_necessaire=20)
        self.assertEqual(ligne.unite, "G")
        fiche.valider(self.admin)
        of = OrdreFabrication.objects.create(article=jus, quantite_a_produire=100, responsable=self.admin)
        self.assertEqual(of.besoins_matieres.get().quantite_theorique, Decimal(2))   # 100 x 20 g = 2 kg


class MachineEtAmortissementTests(BaseValidation):
    def setUp(self):
        super().setUp()
        eau, usine = Activite.objects.get(code="EAU"), Usine.objects.get(code="US-EAU")
        self.ligne = Ligne.objects.create(designation="Ligne Eau 1", usine=usine, activite=eau)
        self.remplissage = Poste.objects.create(ligne=self.ligne, etape=EtapeStandard.objects.get(code="REMPLISSAGE"), ordre=1)
        self.bouchage = Poste.objects.create(ligne=self.ligne, etape=EtapeStandard.objects.get(code="BOUCHAGE"), ordre=2)
        self.machine = Equipement.objects.create(
            designation="Monobloc remplissage-bouchage", type_equipement="REMPLISSEUSE", usine=usine, activite=eau,
            poste=self.remplissage, valeur_acquisition=1200000, duree_amortissement_mois=60, inducteur_amortissement="BOUTEILLES",
        )
        self.machine.postes_supplementaires.add(self.bouchage)

    def test_machine_combinee_acceptee_sur_ses_deux_postes(self):
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin, ligne=self.ligne)
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="EN_PRODUCTION")
        of.refresh_from_db()
        for poste in (self.remplissage, self.bouchage):
            EtapeProduction.objects.create(ordre_fabrication=of, etape=poste.etape.code, poste=poste, equipement=self.machine, agent=self.admin)
        self.assertEqual(of.etapes.count(), 2)

    def test_amortissement_une_seule_fois_avec_son_inducteur(self):
        periode = timezone.localdate().strftime("%Y-%m")
        charges = cascade.generer_amortissements(periode)
        cascade.generer_amortissements(periode)   # idempotent
        self.assertEqual(Charge.objects.filter(equipement=self.machine).count(), 1)
        self.assertEqual((charges[0].montant, charges[0].nature.inducteur), (Decimal("20000.00"), "BOUTEILLES"))


class ControlesTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.eau = Activite.objects.get(code="EAU")
        self.aspect = ParametreQualite.objects.get(libelle="Aspect / couleur")

    def test_controle_obligatoire_non_realise_bloque_la_liberation(self):
        PointControle.objects.create(designation="Aspect fin de ligne", parametre=self.aspect, activite=self.eau,
                                     declencheur="CHAQUE_LOT", obligatoire=True, statut="ACTIF")
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        lot = Lot.objects.create(article=self.produit, ordre_fabrication=of, quantite=10, date_production=date.today())
        refus = self.assert_refus(self.api.post("/api/qualite/controles/", {"lot": lot.id, "resultat": "CONFORME"}, format="json"))
        self.assertIn("obligatoire", str(refus.data))

    def test_point_cree_depuis_la_bibliotheque(self):
        ph = ParametreQualite.objects.get(libelle="pH")
        phmetre = Instrument.objects.create(designation="pH-mètre labo", type_instrument="pH-mètre", grandeur_mesuree="pH", unite="pH")
        modele = ModeleControle.objects.create(designation="pH eau traitée", parametre=ph, instrument=phmetre,
                                               methode="Mesure directe à 20 °C", obligatoire=True)
        r = self.api.post("/api/qualite/plan-controle/", {
            "modele": modele.id, "activite": self.eau.id, "declencheur": "CHAQUE_OF", "valeur_min": "6.5", "valeur_max": "8.5",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["parametre"], r.data["instrument"], r.data["methode"], r.data["obligatoire"], r.data["designation"]),
                         (ph.id, phmetre.id, "Mesure directe à 20 °C", True, "pH eau traitée"))


class DonneesObligatoiresTests(BaseValidation):
    def test_zero_accepte_mais_pas_non_renseigne(self):
        DonneeObligatoireEtape.objects.create(etape=EtapeStandard.objects.get(code="REMPLISSAGE"), champ="quantite_rejetee")
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="EN_PRODUCTION")
        refus = self.assert_refus(self.api.post("/api/production/etapes/", {"ordre_fabrication": of.id, "etape": "REMPLISSAGE"}, format="json"))
        self.assertIn("Quantité rejetée", str(refus.data))
        ok = self.api.post("/api/production/etapes/", {"ordre_fabrication": of.id, "etape": "REMPLISSAGE", "quantite_rejetee": "0"}, format="json")
        self.assertEqual(ok.status_code, 201, ok.content)
