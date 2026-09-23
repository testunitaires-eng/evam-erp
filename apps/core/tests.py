"""
Tests de non-régression de la règle « aucun enregistrement avec erreur ».

Chaque test envoie via l'API une opération qui viole une règle métier
et vérifie DEUX choses :
1. la réponse est une erreur 4xx avec un message (jamais un 500) ;
2. RIEN n'a été écrit en base (ni le document, ni ses effets de bord :
   mouvement de stock, ligne, changement de statut...).

Lancer : python manage.py test apps.core
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.comptes.models import Utilisateur, Profil
from apps.referentiel.models import Article
from apps.fiscalite.models import CodeFiscal, FamilleFiscale
from apps.stocks.models import MouvementStock, StockArticle, depot_par_defaut
from apps.commercial.models import Client, Commande, LigneCommande, Facture, LigneFacture, Avoir
from apps.production.models import OrdreFabrication, SortieMatiere, DemandeMatiere
from apps.caisse.models import Caisse, SessionCaisse, Encaissement
from apps.achats.models import (
    Fournisseur, CommandeFournisseur, LigneCommandeFournisseur, ReceptionAchat, LigneReceptionAchat,
)
from apps.qualite.models import Lot
from apps.distribution.models import PreparationLivraison


class BaseValidation(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_superuser("admin", "admin@evam.test", "x", profil=Profil.ADMIN_SI)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        famille = FamilleFiscale.objects.create(nom="Test")
        self.code_fiscal = CodeFiscal.objects.create(code="FISC", famille_fiscale=famille, taux_tva=18)
        self.produit = Article.objects.create(
            code="PF1", type_article="PRODUIT_FINI", unite_mesure="UNITE", code_fiscal=self.code_fiscal,
        )
        self.matiere = Article.objects.create(code="MP1", type_article="MATIERE_PREMIERE", unite_mesure="KG")
        self.client_evam = Client.objects.create(
            code="C1", nom="Client test", type_client="SOCIETE", encours_autorise=100000,
        )

    # -- utilitaires -------------------------------------------------------
    def entree_stock(self, article, quantite, depot="Magasin principal"):
        MouvementStock.objects.create(
            article=article, depot=depot_par_defaut(depot), type_mouvement="ENTREE",
            quantite=quantite, utilisateur=self.admin,
        )

    def commande(self, lignes=((10, 100),), statut="BROUILLON"):
        commande = Commande.objects.create(client=self.client_evam, type_commande="COMPTANT", cree_par=self.admin)
        for quantite, prix in lignes:
            LigneCommande.objects.create(commande=commande, article=self.produit, quantite=quantite, prix_unitaire=prix)
        if statut != "BROUILLON":
            commande.statut = "VALIDEE"
            commande.save()
        if statut == "EN_PREPARATION":
            commande.statut = "EN_PREPARATION"
            commande.save()
        return commande

    def assert_refus(self, reponse):
        self.assertIn(reponse.status_code, (400, 405, 409), reponse.content)
        return reponse


class CommercialTests(BaseValidation):
    def test_ligne_depassant_encours_non_enregistree(self):
        commande = self.commande(lignes=())
        r = self.api.post("/api/commercial/lignes-commande/", {
            "commande": commande.id, "article": self.produit.id, "quantite": "10", "prix_unitaire": "50000",
        }, format="json")
        self.assert_refus(r)
        self.assertIn("Encours", str(r.data))
        self.assertEqual(LigneCommande.objects.count(), 0)

    def test_ligne_client_bloque_non_enregistree(self):
        commande = self.commande(lignes=())
        self.client_evam.bloque = True
        self.client_evam.save()
        self.assert_refus(self.api.post("/api/commercial/lignes-commande/", {
            "commande": commande.id, "article": self.produit.id, "quantite": "1", "prix_unitaire": "10",
        }, format="json"))
        self.assertEqual(LigneCommande.objects.count(), 0)

    def test_quantite_negative_refusee(self):
        commande = self.commande(lignes=())
        self.assert_refus(self.api.post("/api/commercial/lignes-commande/", {
            "commande": commande.id, "article": self.produit.id, "quantite": "-5", "prix_unitaire": "10",
        }, format="json"))
        self.assertEqual(LigneCommande.objects.count(), 0)

    def test_commande_creee_directement_livree_refusee(self):
        self.assert_refus(self.api.post("/api/commercial/commandes/", {
            "client": self.client_evam.id, "type_commande": "COMPTANT", "statut": "LIVREE",
        }, format="json"))
        self.assertEqual(Commande.objects.count(), 0)

    def test_validation_commande_sans_ligne_refusee(self):
        commande = self.commande(lignes=())
        self.assert_refus(self.api.patch(f"/api/commercial/commandes/{commande.id}/", {"statut": "VALIDEE"}, format="json"))
        commande.refresh_from_db()
        self.assertEqual(commande.statut, "BROUILLON")

    def test_saut_de_statut_refuse(self):
        commande = self.commande()
        self.assert_refus(self.api.patch(f"/api/commercial/commandes/{commande.id}/", {"statut": "FACTUREE"}, format="json"))
        commande.refresh_from_db()
        self.assertEqual(commande.statut, "BROUILLON")

    def test_ligne_sur_commande_en_preparation_refusee(self):
        commande = self.commande(statut="EN_PREPARATION")
        self.assert_refus(self.api.post("/api/commercial/lignes-commande/", {
            "commande": commande.id, "article": self.produit.id, "quantite": "1", "prix_unitaire": "10",
        }, format="json"))
        self.assertEqual(commande.lignes.count(), 1)

    def test_facture_sur_commande_brouillon_refusee(self):
        commande = self.commande()
        self.assert_refus(self.api.post("/api/commercial/factures/", {"commande": commande.id}, format="json"))
        self.assertEqual(Facture.objects.count(), 0)

    def test_generer_lignes_tout_ou_rien(self):
        sans_fiscal = Article.objects.create(code="PF2", type_article="PRODUIT_FINI", unite_mesure="UNITE")
        commande = self.commande()
        LigneCommande.objects.create(commande=commande, article=sans_fiscal, quantite=1, prix_unitaire=10)
        commande.statut = "VALIDEE"
        commande.save()
        facture = Facture.objects.create(commande=commande)
        r = self.assert_refus(self.api.post(f"/api/commercial/factures/{facture.id}/generer_lignes/"))
        self.assertIn("PF2", str(r.data))
        self.assertEqual(LigneFacture.objects.count(), 0)

    def test_generer_lignes_deux_fois_refuse(self):
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        self.assertEqual(self.api.post(f"/api/commercial/factures/{facture.id}/generer_lignes/").status_code, 200)
        self.assert_refus(self.api.post(f"/api/commercial/factures/{facture.id}/generer_lignes/"))
        self.assertEqual(LigneFacture.objects.count(), 1)

    def test_montant_facture_non_modifiable(self):
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        self.api.patch(f"/api/commercial/factures/{facture.id}/", {"montant_total": "1"}, format="json")
        facture.refresh_from_db()
        self.assertEqual(facture.montant_total, 0)
        self.assert_refus(self.api.patch(f"/api/commercial/factures/{facture.id}/", {"statut": "PAYEE"}, format="json"))

    def test_avoir_superieur_au_solde_refuse(self):
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        avoir = Avoir.objects.create(client=self.client_evam, montant=facture.montant_total + 1, motif="x", cree_par=self.admin)
        self.assert_refus(self.api.post(f"/api/commercial/avoirs/{avoir.id}/utiliser/", {"facture": facture.id}, format="json"))
        avoir.refresh_from_db()
        self.assertEqual(avoir.statut, "EMIS")


class StockEtProductionTests(BaseValidation):
    def test_sortie_superieure_au_stock_refusee(self):
        self.entree_stock(self.matiere, 5)
        self.assert_refus(self.api.post("/api/stocks/mouvements/", {
            "article": self.matiere.id, "depot": depot_par_defaut("Magasin principal").id,
            "type_mouvement": "SORTIE", "quantite": "6",
        }, format="json"))
        self.assertEqual(MouvementStock.objects.count(), 1)
        self.assertEqual(StockArticle.objects.get(article=self.matiere).quantite_physique, 5)

    def test_mouvement_non_modifiable(self):
        self.entree_stock(self.matiere, 5)
        mouvement = MouvementStock.objects.get()
        self.assert_refus(self.api.patch(f"/api/stocks/mouvements/{mouvement.id}/", {"quantite": "50"}, format="json"))
        self.assert_refus(self.api.delete(f"/api/stocks/mouvements/{mouvement.id}/"))

    def test_sortie_matiere_of_cloture_ne_touche_pas_le_stock(self):
        self.entree_stock(self.matiere, 10)
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="CLOTURE")
        self.assert_refus(self.api.post("/api/production/sorties-matieres/", {
            "ordre_fabrication": of.id, "matiere": self.matiere.id, "quantite_sortie": "5",
        }, format="json"))
        self.assertEqual(SortieMatiere.objects.count(), 0)
        self.assertEqual(MouvementStock.objects.count(), 1)
        self.assertEqual(StockArticle.objects.get(article=self.matiere).quantite_physique, 10)

    def test_sortie_matiere_stock_insuffisant(self):
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        r = self.assert_refus(self.api.post("/api/production/sorties-matieres/", {
            "ordre_fabrication": of.id, "matiere": self.matiere.id, "quantite_sortie": "5",
        }, format="json"))
        self.assertIn("Stock insuffisant", str(r.data))
        self.assertEqual(SortieMatiere.objects.count(), 0)

    def test_livraison_demande_matiere_pas_de_double_sortie(self):
        self.entree_stock(self.matiere, 100)
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        demande = DemandeMatiere.objects.create(
            ordre_fabrication=of, matiere=self.matiere, quantite_demandee=10, demandeur=self.admin,
        )
        url = f"/api/production/demandes-matieres/{demande.id}/livrer/"
        self.assert_refus(self.api.post(url, {"quantite_livree": "abc"}, format="json"))
        self.assertEqual(SortieMatiere.objects.count(), 0)
        self.assertEqual(self.api.post(url, {"quantite_livree": "4"}, format="json").status_code, 200)
        self.assert_refus(self.api.post(url, {"quantite_livree": "7"}, format="json"))
        self.assertEqual(self.api.post(url, {}, format="json").status_code, 200)
        self.assert_refus(self.api.post(url, {}, format="json"))
        self.assertEqual(SortieMatiere.objects.count(), 2)
        self.assertEqual(StockArticle.objects.get(article=self.matiere).quantite_physique, 90)

    def test_statut_of_non_modifiable_directement(self):
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        self.api.patch(f"/api/production/ordres-fabrication/{of.id}/", {"statut": "CLOTURE"}, format="json")
        of.refresh_from_db()
        self.assertEqual(of.statut, "BROUILLON")


class QualiteTests(BaseValidation):
    def test_lot_ne_peut_pas_etre_libere_deux_fois(self):
        lot = Lot.objects.create(article=self.produit, quantite=10, date_production="2026-09-01")
        r = self.api.post("/api/qualite/controles/", {"lot": lot.id, "resultat": "CONFORME"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        controle_id = r.data["id"]
        self.assertEqual(self.api.post(f"/api/qualite/lots/{lot.id}/liberer/").status_code, 200)
        self.assert_refus(self.api.patch(f"/api/qualite/controles/{controle_id}/", {"resultat": "CONFORME"}, format="json"))
        self.assert_refus(self.api.post(f"/api/qualite/lots/{lot.id}/liberer/"))
        self.assertEqual(StockArticle.objects.get(article=self.produit).quantite_physique, 10)

    def test_statut_lot_non_modifiable_directement(self):
        lot = Lot.objects.create(article=self.produit, quantite=10, date_production="2026-09-01")
        self.api.patch(f"/api/qualite/lots/{lot.id}/", {"statut": "LIBERE"}, format="json")
        lot.refresh_from_db()
        self.assertEqual(lot.statut, "EN_ATTENTE")
        self.assertFalse(StockArticle.objects.filter(article=self.produit).exists())


class CaisseTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.session = SessionCaisse.objects.create(
            caisse=Caisse.objects.create(nom="Caisse 1"), caissier=self.admin, solde_ouverture=0,
        )
        commande = self.commande(statut="VALIDEE")
        self.facture = Facture.objects.create(commande=commande)
        self.facture.generer_lignes_depuis_commande()

    def test_encaissement_superieur_au_solde_refuse(self):
        self.assert_refus(self.api.post("/api/caisse/encaissements/", {
            "session_caisse": self.session.id, "facture": self.facture.id,
            "montant": str(self.facture.montant_total + 1), "mode_paiement": "ESPECES",
        }, format="json"))
        self.assertEqual(Encaissement.objects.count(), 0)

    def test_encaissement_met_a_jour_statut_facture(self):
        r = self.api.post("/api/caisse/encaissements/", {
            "session_caisse": self.session.id, "facture": self.facture.id,
            "montant": str(self.facture.montant_total), "mode_paiement": "ESPECES",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.facture.refresh_from_db()
        self.assertEqual(self.facture.statut, "PAYEE")

    def test_cloture_sans_solde_puis_double_cloture(self):
        url = f"/api/caisse/sessions/{self.session.id}/cloturer/"
        self.assert_refus(self.api.post(url, {}, format="json"))
        self.session.refresh_from_db()
        self.assertEqual(self.session.statut, "OUVERTE")
        self.assertEqual(self.api.post(url, {"solde_compte": "0"}, format="json").status_code, 200)
        self.assert_refus(self.api.post(url, {"solde_compte": "0"}, format="json"))

    def test_encaissement_sur_session_cloturee_refuse(self):
        self.session.cloturer(solde_compte=0)
        self.assert_refus(self.api.post("/api/caisse/encaissements/", {
            "session_caisse": self.session.id, "facture": self.facture.id,
            "montant": "1", "mode_paiement": "ESPECES",
        }, format="json"))
        self.assertEqual(Encaissement.objects.count(), 0)


class AchatsEtDistributionTests(BaseValidation):
    def test_reception_superieure_au_reste_refusee(self):
        commande = CommandeFournisseur.objects.create(
            fournisseur=Fournisseur.objects.create(code="F1", nom="Fournisseur"), cree_par=self.admin,
        )
        ligne = LigneCommandeFournisseur.objects.create(
            commande=commande, article=self.matiere, quantite_commandee=10, prix_unitaire=5,
        )
        commande.envoyer()
        reception = ReceptionAchat.objects.create(commande=commande, receptionne_par=self.admin)
        self.assert_refus(self.api.post("/api/achats/lignes-reception/", {
            "reception": reception.id, "ligne_commande": ligne.id, "quantite_recue": "11",
        }, format="json"))
        self.assertEqual(LigneReceptionAchat.objects.count(), 0)
        self.assertEqual(MouvementStock.objects.count(), 0)
        r = self.api.post("/api/achats/lignes-reception/", {
            "reception": reception.id, "ligne_commande": ligne.id, "quantite_recue": "10",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        commande.refresh_from_db()
        self.assertEqual(commande.statut, "RECUE")
        self.assertEqual(StockArticle.objects.get(article=self.matiere).quantite_physique, 10)

    def test_sortie_magasin_stock_insuffisant_tout_ou_rien(self):
        commande = self.commande(statut="VALIDEE")
        preparation = PreparationLivraison.objects.create(commande=commande, lancee_par=self.admin)
        self.assertEqual(self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_preparation/").status_code, 200)
        self.assert_refus(self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/"))
        preparation.refresh_from_db()
        self.assertEqual(preparation.statut, "EN_PREPARATION")
        self.assertEqual(MouvementStock.objects.count(), 0)

    def test_pas_de_double_sortie_magasin(self):
        self.entree_stock(self.produit, 100, depot="Dépôt produits finis")
        commande = self.commande(statut="VALIDEE")
        preparation = PreparationLivraison.objects.create(commande=commande, lancee_par=self.admin)
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_preparation/")
        self.assertEqual(self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/").status_code, 200)
        self.assert_refus(self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/"))
        self.assertEqual(StockArticle.objects.get(article=self.produit).quantite_physique, Decimal("90"))


class ParametrageTests(BaseValidation):
    def test_depots_et_caisse_crees_par_les_migrations(self):
        from apps.stocks.models import Depot, DEPOTS_SYSTEME
        for nom in DEPOTS_SYSTEME:
            self.assertTrue(Depot.objects.filter(nom=nom, actif=True).exists(), nom)
        self.assertTrue(Caisse.objects.filter(nom="Caisse principale").exists())

    def test_depot_systeme_protege(self):
        depot = depot_par_defaut("Magasin principal")
        url = f"/api/stocks/depots/{depot.id}/"
        self.assertTrue(self.api.get(url).data["est_systeme"])
        self.assert_refus(self.api.patch(url, {"nom": "Dépôt matières premières"}, format="json"))
        self.assert_refus(self.api.patch(url, {"actif": False}, format="json"))
        self.assert_refus(self.api.delete(url))
        depot.refresh_from_db()
        self.assertEqual((depot.nom, depot.actif), ("Magasin principal", True))

    def test_nom_de_depot_en_double_refuse(self):
        self.assert_refus(self.api.post("/api/stocks/depots/", {"nom": "dépôt produits finis"}, format="json"))
        self.assertEqual(self.api.post("/api/stocks/depots/", {"nom": "Dépôt Pointe-Noire"}, format="json").status_code, 201)


class LivraisonEtClientBloqueTests(BaseValidation):
    def test_commande_client_bloque_refusee_par_api(self):
        self.client_evam.bloque = True
        self.client_evam.save()
        r = self.assert_refus(self.api.post("/api/commercial/commandes/", {
            "client": self.client_evam.id, "type_commande": "COMPTANT",
        }, format="json"))
        self.assertIn("bloqué", str(r.data))
        self.assertEqual(Commande.objects.count(), 0)

    def _bon_livraison(self, type_commande="COMPTANT"):
        from apps.distribution.models import BonLivraison
        self.entree_stock(self.produit, 100, depot="Dépôt produits finis")
        commande = self.commande(statut="VALIDEE")
        Commande.objects.filter(pk=commande.pk).update(type_commande=type_commande)
        commande.refresh_from_db()
        preparation = PreparationLivraison.objects.create(commande=commande, lancee_par=self.admin)
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_preparation/")
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/")
        return commande, BonLivraison.objects.create(commande=commande)

    def test_livraison_comptant_refusee_avant_paiement(self):
        commande, bon = self._bon_livraison()
        url = f"/api/distribution/bons-livraison/{bon.id}/confirmer_livraison/"
        self.assertIn("facture", str(self.assert_refus(self.api.post(url)).data))
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        self.assertIn("soldée", str(self.assert_refus(self.api.post(url)).data))
        bon.refresh_from_db()
        self.assertEqual(bon.statut, "EN_LIVRAISON")

        session = SessionCaisse.objects.create(
            caisse=Caisse.objects.create(nom="Caisse test"), caissier=self.admin, solde_ouverture=0,
        )
        Encaissement.objects.create(session_caisse=session, facture=facture, montant=facture.montant_total, mode_paiement="ESPECES")
        self.assertEqual(self.api.post(url).status_code, 200)
        bon.refresh_from_db()
        self.assertEqual(bon.statut, "LIVREE")

    def test_livraison_contrat_sur_facture_emise(self):
        commande, bon = self._bon_livraison(type_commande="CONTRAT")
        url = f"/api/distribution/bons-livraison/{bon.id}/confirmer_livraison/"
        self.assert_refus(self.api.post(url))
        Facture.objects.create(commande=commande).generer_lignes_depuis_commande()
        self.assertEqual(self.api.post(url).status_code, 200)
