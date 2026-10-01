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
from apps.referentiel.models import (
    Article, FicheTechnique, CompositionFicheTechnique, FamilleArticle, FormatArticle, Parfum, UniteVenteArticle,
)
from apps.fiscalite.models import CodeFiscal, FamilleFiscale
from apps.stocks.models import MouvementStock, StockArticle, depot_par_defaut
from apps.commercial.models import Client, Commande, LigneCommande, Facture, LigneFacture, Avoir
from apps.production.models import OrdreFabrication, SortieMatiere, DemandeMatiere
from apps.caisse.models import Caisse, SessionCaisse, Encaissement, EcartCaisse as models_ecart
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
        self.produit = self.nouveau_pf(code_fiscal=self.code_fiscal)   # EAU70P8
        self.matiere = Article.objects.create(code="MP1", type_article="MATIERE_PREMIERE", unite_mesure="KG")
        # Fiche de composition validée du produit : 2 kg de MP1 par unité.
        fiche = FicheTechnique.objects.create(article=self.produit, version=1, cree_par=self.admin)
        CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=self.matiere, quantite_necessaire=2)
        fiche.valider(self.admin)
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

    def nouveau_pf(self, famille="Eau", format="70 cl", unite="Pack de 8", parfum=None, **autres):
        """Produit fini complet (famille, format, unité de vente, parfum éventuel), code calculé automatiquement."""
        return Article.objects.create(
            type_article="PRODUIT_FINI", unite_mesure="UNITE",
            famille=FamilleArticle.objects.get_or_create(nom=famille)[0],
            format=FormatArticle.objects.get_or_create(valeur=format)[0],
            unite_vente=UniteVenteArticle.objects.get_or_create(nom=unite)[0],
            parfum=Parfum.objects.get_or_create(nom=parfum)[0] if parfum else None,
            **autres,
        )

    def ouvrir_caisse(self, nom="Caisse 1"):
        """Crée un caissier, sa caisse, et ouvre sa session. Retourne (session, client API du caissier)."""
        caissier = Utilisateur.objects.create_user(f"caissier_{nom}", password="x", profil=Profil.CAISSIER)
        caisse = Caisse.objects.create(nom=nom, caissier=caissier)
        session = SessionCaisse.objects.create(caisse=caisse, caissier=caissier, solde_ouverture=0)
        api = APIClient()
        api.force_authenticate(caissier)
        return session, api

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
        sans_fiscal = self.nouveau_pf(format="100 cl")
        commande = self.commande()
        LigneCommande.objects.create(commande=commande, article=sans_fiscal, quantite=1, prix_unitaire=10)
        commande.statut = "VALIDEE"
        commande.save()
        facture = Facture.objects.create(commande=commande)
        r = self.assert_refus(self.api.post(f"/api/commercial/factures/{facture.id}/generer_lignes/"))
        self.assertIn(sans_fiscal.code, str(r.data))
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
        self.session, self.api = self.ouvrir_caisse()
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

        session, _ = self.ouvrir_caisse("Caisse test")
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


class CompositionEtDemandeMatieresTests(BaseValidation):
    def test_produit_fini_recoit_sa_fiche_brouillon(self):
        r = self.api.post("/api/referentiel/articles/", {
            "type_article": "PRODUIT_FINI", "unite_mesure": "UNITE",
            "famille": FamilleArticle.objects.get(nom="Eau").id,
            "format": FormatArticle.objects.create(valeur="150 cl").id,
            "unite_vente": UniteVenteArticle.objects.get(nom="Pack de 8").id,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        fiche = FicheTechnique.objects.get(article_id=r.data["id"])
        self.assertEqual((fiche.version, fiche.statut), (1, "BROUILLON"))
        self.assertEqual(r.data["fiche_technique_brouillon"], fiche.id)

    def test_matiere_premiere_sans_fiche(self):
        r = self.api.post("/api/referentiel/articles/", {
            "code": "MP9", "type_article": "MATIERE_PREMIERE", "unite_mesure": "KG",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertFalse(FicheTechnique.objects.filter(article_id=r.data["id"]).exists())

    def test_composition_reservee_admin_si(self):
        fiche = self.produit.creer_fiche_technique_brouillon(self.admin) or FicheTechnique.objects.create(
            article=self.produit, version=2, cree_par=self.admin,
        )
        responsable = Utilisateur.objects.create_user("resp", password="x", profil=Profil.RESPONSABLE_PRODUCTION)
        api = APIClient()
        api.force_authenticate(responsable)
        donnees = {"fiche_technique": fiche.id, "matiere": self.matiere.id, "quantite_necessaire": "1"}
        self.assertEqual(api.post("/api/referentiel/compositions/", donnees, format="json").status_code, 403)
        self.assertEqual(api.get("/api/referentiel/compositions/").status_code, 200)
        self.assertEqual(self.api.post("/api/referentiel/compositions/", donnees, format="json").status_code, 201)

    def test_produit_fini_refuse_dans_une_composition(self):
        fiche = FicheTechnique.objects.create(article=self.produit, version=2, cree_par=self.admin)
        autre_pf = self.nouveau_pf(format="150 cl")
        self.assert_refus(self.api.post("/api/referentiel/compositions/", {
            "fiche_technique": fiche.id, "matiere": autre_pf.id, "quantite_necessaire": "1",
        }, format="json"))

    def test_of_refuse_sans_fiche_validee(self):
        sans_fiche = self.nouveau_pf(unite="Carton de 12")
        r = self.assert_refus(self.api.post("/api/production/ordres-fabrication/", {
            "article": sans_fiche.id, "quantite_a_produire": "10",
        }, format="json"))
        self.assertIn("composition", str(r.data))
        self.assertEqual(OrdreFabrication.objects.count(), 0)

    def test_demande_de_toute_la_composition(self):
        emballage = Article.objects.create(code="EMB1", type_article="MATIERE_PREMIERE", unite_mesure="UNITE")
        fiche = FicheTechnique.objects.create(article=self.produit, version=2, cree_par=self.admin)
        CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=self.matiere, quantite_necessaire=Decimal("0.5"))
        CompositionFicheTechnique.objects.create(fiche_technique=fiche, matiere=emballage, quantite_necessaire=1)
        fiche.valider(self.admin)
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=100, responsable=self.admin)

        url = f"/api/production/ordres-fabrication/{of.id}/demander_matieres/"
        r = self.api.post(url)
        self.assertEqual(r.status_code, 201, r.content)
        demandes = {d.matiere.code: d.quantite_demandee for d in DemandeMatiere.objects.filter(ordre_fabrication=of)}
        self.assertEqual(demandes, {"MP1": Decimal("50"), "EMB1": Decimal("100")})
        self.assert_refus(self.api.post(url))
        self.assertEqual(DemandeMatiere.objects.count(), 2)

    def test_demande_matiere_manuelle_refusee(self):
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        self.assert_refus(self.api.post("/api/production/demandes-matieres/", {
            "ordre_fabrication": of.id, "matiere": self.matiere.id, "quantite_demandee": "5",
        }, format="json"))
        self.assertEqual(DemandeMatiere.objects.count(), 0)


class CodificationAutomatiqueTests(BaseValidation):
    def test_codes_generes_et_code_saisi_ignore(self):
        r = self.api.post("/api/commercial/clients/", {
            "code": "MON-CODE", "nom": "Boutique", "type_client": "PARTICULIER",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertRegex(r.data["code"], r"^CLI-\d{6}$")
        r2 = self.api.patch(f"/api/commercial/clients/{r.data['id']}/", {"code": "AUTRE"}, format="json")
        self.assertEqual(r2.data["code"], r.data["code"])

        r = self.api.post("/api/achats/fournisseurs/", {"nom": "Emballages SA"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertRegex(r.data["code"], r"^FRS-\d{6}$")

    def test_code_article_selon_le_type(self):
        for type_article, prefixe in (("MATIERE_PREMIERE", "MP"), ("PRODUIT_INTERMEDIAIRE", "PI")):
            r = self.api.post("/api/referentiel/articles/", {"type_article": type_article, "unite_mesure": "UNITE"}, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            self.assertRegex(r.data["code"], rf"^{prefixe}-\d{{6}}$")

    def test_code_article_saute_un_code_deja_pris(self):
        Article.objects.create(code="MP-000001", type_article="MATIERE_PREMIERE", unite_mesure="KG")
        r = self.api.post("/api/referentiel/articles/", {"type_article": "MATIERE_PREMIERE", "unite_mesure": "KG"}, format="json")
        self.assertEqual(r.data["code"], "MP-000002")

    def test_code_fiscal_selon_la_matrice(self):
        jus = FamilleFiscale.objects.create(nom="Jus EVAM sucré/aromatisé")
        eau = FamilleFiscale.objects.create(nom="Eau minérale produite au Congo")
        cas = [
            ({"famille_fiscale": jus.id, "taux_tva": "18", "taux_accise": "10"}, "EV-FISC-JUS-18"),
            ({"famille_fiscale": eau.id, "exonere": True}, "EV-FISC-EAU-0"),
            ({"famille_fiscale": eau.id, "taux_tva": "18"}, "EV-FISC-EAU-18"),
            ({"famille_fiscale": eau.id, "taux_tva": "18"}, "EV-FISC-EAU-18-2"),
        ]
        for donnees, attendu in cas:
            r = self.api.post("/api/fiscalite/codes-fiscaux/", donnees, format="json")
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(r.data["code"], attendu)


class ChoixCompositionTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.pf = self.nouveau_pf(famille="Jus", parfum="Orange")
        self.fiche = FicheTechnique.objects.create(article=self.pf, version=1, cree_par=self.admin)
        self.bouteille = Article.objects.create(code="PI5", type_article="PRODUIT_INTERMEDIAIRE", unite_mesure="UNITE")
        Article.objects.create(code="MP5", type_article="MATIERE_PREMIERE", unite_mesure="KG", actif=False)
        self.base = f"/api/referentiel/fiches-techniques/{self.fiche.id}/"

    def test_elements_disponibles_lus_en_base(self):
        codes = {e["code"] for e in self.api.get(self.base + "elements_disponibles/").data}
        self.assertEqual(codes, {"MP1", "PI5"})  # ni produit fini, ni inactif
        CompositionFicheTechnique.objects.create(fiche_technique=self.fiche, matiere=self.matiere, quantite_necessaire=1)
        codes = {e["code"] for e in self.api.get(self.base + "elements_disponibles/").data}
        self.assertEqual(codes, {"PI5"})  # déjà dans la composition : retiré de la liste

    def test_ajout_groupe_et_infos_reprises_de_la_base(self):
        r = self.api.post(self.base + "ajouter_elements/", {"elements": [
            {"matiere": self.matiere.id, "quantite_necessaire": "0.5"},
            {"matiere": self.bouteille.id, "quantite_necessaire": "1"},
        ]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        lignes = {l["matiere_code"]: (l["matiere_designation"], l["unite_mesure"]) for l in r.data["composition"]}
        self.assertEqual(lignes["MP1"], (self.matiere.designation, "KG"))

    def test_ajout_groupe_tout_ou_rien(self):
        r = self.assert_refus(self.api.post(self.base + "ajouter_elements/", {"elements": [
            {"matiere": self.matiere.id, "quantite_necessaire": "0.5"},
            {"matiere": self.produit.id, "quantite_necessaire": "1"},
            {"matiere": 99999, "quantite_necessaire": "1"},
        ]}, format="json"))
        self.assertIn("element_2", r.data)
        self.assertIn("element_3", r.data)
        self.assertEqual(self.fiche.composition.count(), 0)


class CaissePrincipaleTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.principale = Caisse.principale()
        commande = self.commande(statut="VALIDEE")
        self.facture = Facture.objects.create(commande=commande)
        self.facture.generer_lignes_depuis_commande()   # 1 000 HT -> 1 180 TTC

    def encaisser(self, api, session, montant):
        return api.post("/api/caisse/encaissements/", {
            "session_caisse": session.id, "facture": self.facture.id,
            "montant": str(montant), "mode_paiement": "ESPECES",
        }, format="json")

    def test_caisse_principale_protegee(self):
        self.assertIsNotNone(self.principale)
        url = f"/api/caisse/caisses/{self.principale.id}/"
        self.assert_refus(self.api.delete(url))
        self.assert_refus(self.api.patch(url, {"actif": False}, format="json"))
        caissier = Utilisateur.objects.create_user("c1", password="x", profil=Profil.CAISSIER)
        self.assert_refus(self.api.patch(url, {"caissier": caissier.id}, format="json"))
        api = APIClient()
        api.force_authenticate(caissier)
        self.assert_refus(api.post("/api/caisse/sessions/", {"caisse": self.principale.id}, format="json"))

    def test_ouverture_sur_sa_propre_caisse_uniquement(self):
        caissier = Utilisateur.objects.create_user("c1", password="x", profil=Profil.CAISSIER)
        api = APIClient()
        api.force_authenticate(caissier)
        self.assertIn("Aucune caisse", str(self.assert_refus(api.post("/api/caisse/sessions/", {}, format="json")).data))

        r = self.api.post("/api/caisse/caisses/", {"nom": "Caisse Nord", "caissier": caissier.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        autre_session, _ = self.ouvrir_caisse("Caisse Sud")
        self.assert_refus(api.post("/api/caisse/sessions/", {"caisse": autre_session.caisse_id}, format="json"))

        r = api.post("/api/caisse/sessions/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["caisse"], r.data["solde_ouverture"]), (Caisse.objects.get(nom="Caisse Nord").id, "0.00"))

    def test_encaissement_par_un_autre_caissier_refuse(self):
        session, _ = self.ouvrir_caisse("Caisse A")
        _, api_autre = self.ouvrir_caisse("Caisse B")
        self.assert_refus(self.encaisser(api_autre, session, 100))
        self.assertEqual(Encaissement.objects.count(), 0)

    def test_ecart_justifie_a_la_cloture_et_report_du_solde(self):
        session, api = self.ouvrir_caisse()
        self.assertEqual(self.encaisser(api, session, 1000).status_code, 201)
        url = f"/api/caisse/sessions/{session.id}/cloturer/"

        r = self.assert_refus(api.post(url, {"solde_compte": "950"}, format="json"))
        self.assertIn("justification est obligatoire", str(r.data))
        session.refresh_from_db()
        self.assertEqual(session.statut, "OUVERTE")
        self.assert_refus(api.post("/api/caisse/ecarts/", {"session_caisse": session.id, "justification": "x"}, format="json"))

        r = api.post(url, {"solde_compte": "950", "justification": "Erreur de rendu monnaie"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        session.refresh_from_db()
        self.assertEqual((session.statut, session.solde_theorique_cloture), ("CLOTUREE", Decimal("1000")))
        self.assertEqual(session.justification_ecart.montant_ecart, Decimal("-50"))

        # Lendemain : le solde d'ouverture reprend le COMPTÉ de la veille (950),
        # l'écart justifié ne se reporte pas.
        self.assertEqual(Caisse.principale().solde_actuel, Decimal("950"))
        r = api.post("/api/caisse/sessions/", {}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.data["solde_ouverture"]), Decimal("950"))
        nouvelle = SessionCaisse.objects.get(pk=r.data["id"])
        self.assertEqual(self.encaisser(api, nouvelle, 180).status_code, 201)
        r = api.post(f"/api/caisse/sessions/{nouvelle.id}/cloturer/", {"solde_compte": "1130"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)   # 950 + 180 = 1130 : aucun écart
        self.assertFalse(models_ecart.objects.filter(session_caisse=nouvelle).exists())

    def test_montant_global_et_journal_sur_la_caisse_principale(self):
        session_a, api_a = self.ouvrir_caisse("Caisse A")
        session_b, api_b = self.ouvrir_caisse("Caisse B")
        self.assertEqual(self.encaisser(api_a, session_a, 700).status_code, 201)
        self.assertEqual(self.encaisser(api_b, session_b, 300).status_code, 201)

        r = self.api.get("/api/caisse/caisses/principale/")
        self.assertEqual(Decimal(r.data["montant_global"]), Decimal("1000"))
        self.assertEqual({c["nom"]: Decimal(c["solde"]) for c in r.data["caisses"]},
                         {"Caisse A": Decimal("700"), "Caisse B": Decimal("300")})

        journal = self.api.get(f"/api/caisse/caisses/{self.principale.id}/journal/").data
        self.assertEqual(len(journal["operations"]), 2)
        self.assertEqual({(o["caisse"], o["caissier"]) for o in journal["operations"]},
                         {("Caisse A", "caissier_Caisse A"), ("Caisse B", "caissier_Caisse B")})
        self.assertEqual(api_a.get("/api/caisse/caisses/principale/").status_code, 403)
        self.assertIn(api_a.get(f"/api/caisse/caisses/{session_b.caisse_id}/journal/").status_code, (403, 404))
        self.assertEqual(len(api_a.get(f"/api/caisse/caisses/{session_a.caisse_id}/journal/").data["operations"]), 1)


class CodificationProduitsFinisTests(BaseValidation):
    def creer(self, **champs):
        donnees = {"type_article": "PRODUIT_FINI", "unite_mesure": "UNITE"}
        for champ, (modele, attribut) in {
            "famille": (FamilleArticle, "nom"), "format": (FormatArticle, "valeur"),
            "unite_vente": (UniteVenteArticle, "nom"), "parfum": (Parfum, "nom"),
        }.items():
            if champ in champs:
                donnees[champ] = modele.objects.get_or_create(**{attribut: champs[champ]})[0].id
        return self.api.post("/api/referentiel/articles/", donnees, format="json")

    def test_formats_de_code(self):
        cas = [
            ({"famille": "Eau", "format": "100 cl", "unite_vente": "Carton de 12"}, "EAU100C12"),
            ({"famille": "Jus", "parfum": "Grenadine", "format": "70 cl", "unite_vente": "Pack de 8"}, "JUSGRE70P8"),
            ({"famille": "Yaourt", "parfum": "Fraise", "format": "125 g", "unite_vente": "Pot"}, "YAOFRA125POT"),
            ({"famille": "Yaourt", "parfum": "Nature", "format": "125 g", "unite_vente": "Unité"}, "YAO125U"),
        ]
        for champs, attendu in cas:
            r = self.creer(**champs)
            self.assertEqual(r.status_code, 201, r.content)
            self.assertEqual(r.data["code"], attendu)
        self.assertEqual(self.produit.code, "EAU70P8")

    def test_champs_obligatoires_et_parfum(self):
        self.assertIn("unite_vente", self.assert_refus(self.creer(famille="Eau", format="70 cl")).data)
        self.assertIn("parfum", self.assert_refus(self.creer(famille="Jus", format="70 cl", unite_vente="Pack de 8")).data)

    def test_produit_en_double_refuse(self):
        r = self.assert_refus(self.creer(famille="Eau", format="70 cl", unite_vente="Pack de 8"))
        self.assertIn("EAU70P8", str(r.data))

    def test_code_recalcule_tant_que_non_utilise_puis_fige(self):
        url = f"/api/referentiel/articles/{self.produit.id}/"
        format_100 = FormatArticle.objects.create(valeur="100 cl")
        r = self.api.patch(url, {"format": format_100.id}, format="json")
        self.assertEqual((r.status_code, r.data["code"]), (200, "EAU100P8"))
        self.entree_stock(self.produit, 5, depot="Dépôt produits finis")   # article désormais utilisé
        format_150 = FormatArticle.objects.create(valeur="150 cl")
        self.assert_refus(self.api.patch(url, {"format": format_150.id}, format="json"))
        self.assertEqual(self.api.patch(url, {"stock_minimum": "3"}, format="json").data["code"], "EAU100P8")


class AutorisationDecaissementTests(BaseValidation):
    def test_circuit_demande_autorisation_sortie(self):
        session, api = self.ouvrir_caisse()
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        Encaissement.objects.create(session_caisse=session, facture=facture, montant=500, mode_paiement="ESPECES")
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF, first_name="Awa", last_name="Kodia")
        api_daf = APIClient()
        api_daf.force_authenticate(daf)
        Utilisateur.objects.create_user("dg", password="x", profil=Profil.DIRECTION)
        Utilisateur.objects.create_user("dg_parti", password="x", profil=Profil.DIRECTION, is_active=False)
        self.assertEqual({p["username"] for p in api.get("/api/caisse/decaissements/autorisateurs/").data}, {"daf", "dg"})

        # 1. Demande du caissier : l'argent ne sort pas encore.
        r = api.post("/api/caisse/decaissements/", {"session_caisse": session.id, "montant": "100", "motif": "Achat fournitures"}, format="json")
        self.assertEqual((r.status_code, r.data.get("statut")), (201, "EN_ATTENTE"), r.content)
        demande = r.data["id"]
        session.refresh_from_db()
        self.assertEqual(session.calculer_solde_theorique(), Decimal("500"))
        self.assert_refus(api.post(f"/api/caisse/decaissements/{demande}/effectuer/"))       # pas encore autorisé
        self.assertEqual(api.post(f"/api/caisse/decaissements/{demande}/autoriser/").status_code, 403)  # le caissier n'autorise pas

        # 2. Écran « À autoriser » de la DAF, refus sans motif interdit, puis autorisation.
        self.assertEqual([d["id"] for d in api_daf.get("/api/caisse/decaissements/a_autoriser/").data], [demande])
        self.assert_refus(api_daf.post(f"/api/caisse/decaissements/{demande}/refuser/", {}, format="json"))
        r = api_daf.post(f"/api/caisse/decaissements/{demande}/autoriser/")
        self.assertEqual((r.data["statut"], r.data["autorise_par_nom"]), ("AUTORISE", "Awa Kodia"))

        # 3. Le caissier effectue la sortie : le solde baisse, c'est tracé.
        r = api.post(f"/api/caisse/decaissements/{demande}/effectuer/")
        self.assertEqual(r.data["statut"], "EFFECTUE", r.content)
        self.assertEqual(session.calculer_solde_theorique(), Decimal("400"))
        self.assert_refus(api.post(f"/api/caisse/decaissements/{demande}/effectuer/"))       # pas deux fois
        historique = [h["nouveau_statut"] for h in api.get(f"/api/caisse/decaissements/{demande}/historique/").data]
        self.assertEqual(historique, ["En attente d'autorisation", "Autorisé", "Effectué"])

    def test_refus_avec_motif(self):
        session, api = self.ouvrir_caisse()
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        api_daf = APIClient()
        api_daf.force_authenticate(daf)
        demande = api.post("/api/caisse/decaissements/", {"session_caisse": session.id, "montant": "50", "motif": "x"}, format="json").data["id"]
        r = api_daf.post(f"/api/caisse/decaissements/{demande}/refuser/", {"motif": "Non justifié"}, format="json")
        self.assertEqual((r.data["statut"], r.data["motif_refus"]), ("REFUSE", "Non justifié"))
        self.assert_refus(api_daf.post(f"/api/caisse/decaissements/{demande}/autoriser/"))

class AgentProductionTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.agent = Utilisateur.objects.create_user("agent", password="x", profil=Profil.AGENT_PRODUCTION)
        self.api_agent = APIClient()
        self.api_agent.force_authenticate(self.agent)
        self.responsable = Utilisateur.objects.create_user("resp", password="x", profil=Profil.RESPONSABLE_PRODUCTION)
        self.api_resp = APIClient()
        self.api_resp.force_authenticate(self.responsable)
        self.mon_of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        self.autre_of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        self.mon_of.affecter_agents([self.agent], par=self.responsable)

    def demarrer(self, of):
        OrdreFabrication.objects.filter(pk=of.pk).update(statut="EN_PRODUCTION")
        of.refresh_from_db()

    def perte(self, of):
        return self.api_agent.post("/api/production/pertes/", {
            "ordre_fabrication": of.id, "quantite_perte": "3", "motif": "CASSE",
        }, format="json")

    def test_of_en_lecture_seule_et_filtres(self):
        self.assertEqual(self.api_agent.post("/api/production/ordres-fabrication/", {
            "article": self.produit.id, "quantite_a_produire": "5",
        }, format="json").status_code, 403)
        url = f"/api/production/ordres-fabrication/{self.mon_of.id}/"
        self.assertEqual(self.api_agent.patch(url, {"quantite_a_produire": "99"}, format="json").status_code, 403)
        self.assertEqual(self.api_agent.delete(url).status_code, 403)
        self.assertEqual([o["id"] for o in self.api_agent.get("/api/production/ordres-fabrication/").data["results"]], [self.mon_of.id])
        self.assertEqual(self.api_agent.get("/api/production/tableau-de-bord/").data["detail_par_statut"], {"BROUILLON": 1})

    def test_saisie_uniquement_sur_son_of_en_production(self):
        self.assert_refus_ou_interdit(self.perte(self.mon_of))            # OF pas démarré
        self.demarrer(self.mon_of)
        self.demarrer(self.autre_of)
        self.assertEqual(self.perte(self.autre_of).status_code, 403)      # OF non affecté
        r = self.perte(self.mon_of)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["saisi_par_nom"], "agent")
        url = f"/api/production/pertes/{r.data['id']}/"
        self.assertEqual(self.api_agent.patch(url, {"quantite_perte": "1"}, format="json").status_code, 403)
        self.assertEqual(self.api_agent.delete(url).status_code, 403)
        self.assertEqual(self.api_resp.patch(url, {"quantite_perte": "1"}, format="json").status_code, 200)

    def test_personne_ne_saisit_avant_le_demarrage(self):
        self.assert_refus(self.api_resp.post("/api/production/pertes/", {
            "ordre_fabrication": self.mon_of.id, "quantite_perte": "3", "motif": "CASSE",
        }, format="json"))

    def test_donnees_des_autres_of_invisibles(self):
        from apps.production.models import DemandeComplementaire, SuiviEau
        self.demarrer(self.autre_of)
        SuiviEau.objects.create(ordre_fabrication=self.autre_of, volume_capte_l=10, volume_obtenu_traitement_l=9,
                                volume_envoye_embouteillage_l=8, bouteilles_produites=5, bouteilles_conformes=5)
        DemandeComplementaire.objects.create(ordre_fabrication=self.autre_of, matiere=self.matiere, quantite=1,
                                             motif="x", demandeur=self.admin)
        self.assertEqual(self.api_agent.get("/api/production/suivis-eau/").data["count"], 0)
        self.assertEqual(self.api_agent.get("/api/production/demandes-complementaires/").data["count"], 0)

    def test_demande_complementaire_pendant_la_production(self):
        donnees = {"ordre_fabrication": self.mon_of.id, "matiere": self.matiere.id, "quantite": "2", "motif": "Défauts au soufflage"}
        self.assert_refus_ou_interdit(self.api_agent.post("/api/production/demandes-complementaires/", donnees, format="json"))
        self.demarrer(self.mon_of)
        r = self.api_agent.post("/api/production/demandes-complementaires/", donnees, format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_affectation_par_le_responsable_tracee(self):
        from apps.comptes.models import JournalAction
        url = f"/api/production/ordres-fabrication/{self.autre_of.id}/affecter_agents/"
        self.assertEqual(self.api_agent.post(url, {"agents": [self.agent.id]}, format="json").status_code, 403)
        caissier = Utilisateur.objects.create_user("caissier", password="x", profil=Profil.CAISSIER)
        self.assert_refus(self.api_resp.post(url, {"agents": [caissier.id]}, format="json"))
        r = self.api_resp.post(url, {"agents": [self.agent.id]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["agents_affectes_noms"], ["agent"])
        trace = JournalAction.objects.get(document_id=self.autre_of.numero, action__startswith="Ajout")
        self.assertEqual(trace.utilisateur, self.responsable)
        self.assertIn("agent", trace.nouvelle_valeur)
        agents = self.api_resp.get("/api/production/ordres-fabrication/agents_disponibles/").data
        self.assertEqual([a["username"] for a in agents], ["agent"])

    def test_agents_affectes_a_la_conversion_du_plan(self):
        from apps.production.models import PlanProduction
        plan = PlanProduction.objects.create(article=self.produit, date_prevue="2026-10-01", quantite_prevue=50, cree_par=self.responsable)
        r = self.api_resp.post(f"/api/production/plans/{plan.id}/convertir_en_of/", {"agents_affectes": [self.agent.id]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["agents_affectes"], [self.agent.id])

    def assert_refus_ou_interdit(self, reponse):
        self.assertIn(reponse.status_code, (400, 403), reponse.content)


class MatriceAccesTests(BaseValidation):
    def client_pour(self, profil, nom=None):
        utilisateur = Utilisateur.objects.create_user(nom or profil.lower(), password="x", profil=profil)
        api = APIClient()
        api.force_authenticate(utilisateur)
        return utilisateur, api

    def test_modules_invisibles_selon_le_role(self):
        _, caissier = self.client_pour(Profil.CAISSIER)
        _, agent = self.client_pour(Profil.AGENT_PRODUCTION)
        _, chauffeur = self.client_pour(Profil.CHAUFFEUR)
        self.assertEqual(caissier.get("/api/referentiel/articles/").status_code, 403)
        self.assertEqual(caissier.get("/api/production/ordres-fabrication/").status_code, 403)
        self.assertEqual(agent.get("/api/stocks/stock-articles/").status_code, 403)
        self.assertEqual(agent.get("/api/commercial/commandes/").status_code, 403)
        self.assertEqual(chauffeur.get("/api/commercial/tarifs/").status_code, 403)
        self.assertEqual(caissier.get("/api/commercial/commandes/").status_code, 200)   # 👁 à encaisser

    def test_lecture_seule_ne_permet_pas_d_ecrire(self):
        _, distribution = self.client_pour(Profil.RESPONSABLE_DISTRIBUTION)
        commande = self.commande(statut="VALIDEE")
        lignes = distribution.get(f"/api/commercial/lignes-commande/?commande={commande.id}").data["results"]
        self.assertEqual((lignes[0]["article_code"], lignes[0]["stock_disponible"]), ("EAU70P8", 0))
        self.assertEqual(distribution.patch(f"/api/commercial/commandes/{commande.id}/", {"statut": "ANNULEE"}, format="json").status_code, 403)

    def test_annuaire_des_noms_pour_tous(self):
        _, chauffeur = self.client_pour(Profil.CHAUFFEUR)
        Utilisateur.objects.create_user("awa", password="x", profil=Profil.COMPTABILITE_DAF, first_name="Awa", last_name="Kodia")
        noms = {c["username"]: c["nom"] for c in chauffeur.get("/api/comptes/annuaire/").data}
        self.assertEqual(noms["awa"], "Awa Kodia")
        self.assertNotIn("email", chauffeur.get("/api/comptes/annuaire/").data[0])

    def test_article_verrouille_une_fois_utilise(self):
        url = f"/api/referentiel/articles/{self.produit.id}/"
        self.assertFalse(self.api.get(url).data["est_verrouille"])
        self.entree_stock(self.produit, 1, depot="Dépôt produits finis")
        self.assertTrue(self.api.get(url).data["est_verrouille"])

    def test_chauffeur_mes_livraisons(self):
        from apps.distribution.models import BonLivraison, Chauffeur, Tournee, Vehicule
        utilisateur, chauffeur = self.client_pour(Profil.CHAUFFEUR)
        tournee = Tournee.objects.create(
            chauffeur=Chauffeur.objects.create(utilisateur=utilisateur),
            vehicule=Vehicule.objects.create(immatriculation="AB-123"), date_tournee="2026-10-01",
        )
        self.entree_stock(self.produit, 100, depot="Dépôt produits finis")
        commande = self.commande(statut="VALIDEE")
        preparation = PreparationLivraison.objects.create(commande=commande, lancee_par=self.admin)
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_preparation/")
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/")
        bon = BonLivraison.objects.create(commande=commande, tournee=tournee)
        autre = self.commande(statut="VALIDEE")   # BL sans tournée du chauffeur : invisible pour lui
        preparation = PreparationLivraison.objects.create(commande=autre, lancee_par=self.admin)
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_preparation/")
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/")
        BonLivraison.objects.create(commande=autre)

        mes = chauffeur.get("/api/distribution/bons-livraison/mes_livraisons/").data
        self.assertEqual([(b["numero"], b["client_nom"], b["statut_paiement"]) for b in mes],
                         [(bon.numero, "Client test", "Non facturée")])
        self.assertEqual(chauffeur.patch(f"/api/distribution/bons-livraison/{bon.id}/", {"statut": "RETOURNEE"}, format="json").status_code, 403)
        self.assert_refus(chauffeur.post(f"/api/distribution/bons-livraison/{bon.id}/probleme/", {}, format="json"))
        self.assertEqual(chauffeur.post(f"/api/distribution/bons-livraison/{bon.id}/livre/").status_code, 200)
        bon.refresh_from_db()
        self.assertEqual((bon.signature_client, bon.statut), (True, "EN_LIVRAISON"))   # confirmation finale : Resp. Distribution


class HistoriqueTests(BaseValidation):
    def test_historique_commande_et_facture(self):
        commercial = Utilisateur.objects.create_user("com", password="x", profil=Profil.COMMERCIAL, first_name="Jean", last_name="Mavoungou")
        api = APIClient()
        api.force_authenticate(commercial)
        r = api.post("/api/commercial/commandes/", {"client": self.client_evam.id, "type_commande": "COMPTANT"}, format="json")
        commande_id = r.data["id"]
        api.post("/api/commercial/lignes-commande/", {"commande": commande_id, "article": self.produit.id, "quantite": "1", "prix_unitaire": "100"}, format="json")
        api.patch(f"/api/commercial/commandes/{commande_id}/", {"statut": "VALIDEE"}, format="json")
        self.assert_refus(api.patch(f"/api/commercial/commandes/{commande_id}/", {"statut": "LIVREE"}, format="json"))

        historique = api.get(f"/api/commercial/commandes/{commande_id}/historique/").data
        self.assertEqual(
            [(h["action"], h["ancien_statut"], h["nouveau_statut"], h["par"]) for h in historique],
            [("Création", "", "Brouillon", "Jean Mavoungou"), ("Changement de statut", "Brouillon", "Validée", "Jean Mavoungou")],
        )   # le passage refusé n'a laissé aucune trace

        facture = Facture.objects.create(commande_id=commande_id)
        facture.generer_lignes_depuis_commande()
        session, api_caissier = self.ouvrir_caisse()
        api_caissier.post("/api/caisse/encaissements/", {
            "session_caisse": session.id, "facture": facture.id, "montant": str(facture.montant_total), "mode_paiement": "ESPECES",
        }, format="json")
        derniere = api.get(f"/api/commercial/factures/{facture.id}/historique/").data[-1]
        self.assertEqual((derniere["nouveau_statut"], derniere["par"]), ("Payée", "caissier_Caisse 1"))


class BesoinAutomatiqueTests(BaseValidation):
    def sortie(self, quantite):
        MouvementStock.objects.create(
            article=self.preforme, depot=depot_par_defaut("Magasin principal"), type_mouvement="SORTIE",
            quantite=quantite, utilisateur=self.admin,
        )

    def test_besoin_cree_sous_le_seuil_puis_demande_d_achat(self):
        from apps.achats.models import BesoinApprovisionnement, DemandeAchat
        self.preforme = Article.objects.create(type_article="MATIERE_PREMIERE", unite_mesure="UNITE", stock_alerte=100)
        self.entree_stock(self.preforme, 150)
        self.sortie(40)
        self.assertFalse(BesoinApprovisionnement.objects.exists())          # 110 >= 100
        self.sortie(40)                                                     # 70 < 100
        besoin = BesoinApprovisionnement.objects.get()
        self.assertEqual((besoin.origine, besoin.quantite_besoin, besoin.satisfait), ("SEUIL_ALERTE", Decimal("30"), False))
        self.sortie(10)                                                     # 60 : même besoin mis à jour
        besoin.refresh_from_db()
        self.assertEqual((BesoinApprovisionnement.objects.count(), besoin.quantite_besoin), (1, Decimal("40")))

        acheteur = Utilisateur.objects.create_user("achat", password="x", profil=Profil.RESPONSABLE_ACHATS)
        api = APIClient()
        api.force_authenticate(acheteur)
        r = api.post(f"/api/achats/besoins/{besoin.id}/creer_demande/")
        self.assertEqual((r.status_code, Decimal(r.data["quantite_demandee"])), (201, Decimal("40")), r.content)
        self.assert_refus(api.post(f"/api/achats/besoins/{besoin.id}/creer_demande/"))
        DemandeAchat.objects.get().rejeter(acheteur)                         # rejet : le besoin revient à traiter
        besoin.refresh_from_db()
        self.assertFalse(besoin.satisfait)

    def test_besoin_solde_si_le_stock_remonte(self):
        from apps.achats.models import BesoinApprovisionnement
        self.preforme = Article.objects.create(type_article="MATIERE_PREMIERE", unite_mesure="UNITE", stock_alerte=100)
        self.entree_stock(self.preforme, 50)
        self.assertEqual(BesoinApprovisionnement.objects.filter(satisfait=False).count(), 1)
        self.entree_stock(self.preforme, 60)
        self.assertEqual(BesoinApprovisionnement.objects.filter(satisfait=False).count(), 0)


class ComptabiliteTests(BaseValidation):
    def ecriture(self, document):
        from apps.comptabilite.ecritures import ecritures_de
        return {(l.compte, l.compte_tiers, l.debit, l.credit) for e in ecritures_de(document) for l in e.lignes.all()}

    def test_chaine_vente_encaissement_annulation(self):
        from apps.comptabilite.models import CompteParametre, EcritureComptable
        commande = self.commande(statut="VALIDEE")          # 10 x 100 HT, TVA 18 %
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        self.assertEqual(self.ecriture(facture), {
            ("411", self.client_evam.code, Decimal("1180.00"), Decimal("0")),
            ("702", "", Decimal("0"), Decimal("1000.00")),
            ("4431", "", Decimal("0"), Decimal("180.00")),
        })

        CompteParametre.objects.filter(cle="CAISSE").update(numero="5711")      # paramétrage DAF
        session, api = self.ouvrir_caisse()
        api.post("/api/caisse/encaissements/", {
            "session_caisse": session.id, "facture": facture.id, "montant": "500", "mode_paiement": "ESPECES",
        }, format="json")
        encaissement = Encaissement.objects.get()
        self.assertEqual(self.ecriture(encaissement), {
            ("5711", "", Decimal("500.00"), Decimal("0")), ("411", self.client_evam.code, Decimal("0"), Decimal("500.00")),
        })

        for ecriture in EcritureComptable.objects.prefetch_related("lignes"):
            lignes = list(ecriture.lignes.all())
            self.assertEqual(sum(l.debit for l in lignes), sum(l.credit for l in lignes))

        # Facture non payée annulée : contre-passation (solde du compte client revient à 0).
        autre = Facture.objects.create(commande=self.commande(statut="VALIDEE"))
        autre.generer_lignes_depuis_commande()
        autre.statut = "ANNULEE"
        autre.save()
        from apps.comptabilite.models import LigneEcriture
        lignes = LigneEcriture.objects.filter(ecriture__piece=autre.numero, compte="411")
        self.assertEqual(sum(l.debit - l.credit for l in lignes), 0)

    def test_periode_cloturee_bloque_le_document(self):
        from django.utils import timezone
        from apps.comptabilite.models import Cloture
        Cloture.objects.create(type_cloture="MENSUELLE", periode=timezone.localdate().strftime("%Y-%m"), valide_par=self.admin)
        facture = Facture.objects.create(commande=self.commande(statut="VALIDEE"))
        r = self.assert_refus(self.api.post(f"/api/commercial/factures/{facture.id}/generer_lignes/"))
        self.assertIn("clôturée", str(r.data))
        self.assertEqual(LigneFacture.objects.count(), 0)                  # rien n'a été enregistré

    def test_export_sage(self):
        from apps.comptabilite.models import ExportComptable
        from django.utils import timezone
        facture = Facture.objects.create(commande=self.commande(statut="VALIDEE"))
        facture.generer_lignes_depuis_commande()
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        api = APIClient()
        api.force_authenticate(daf)
        aujourd_hui = timezone.localdate()
        r = api.post("/api/comptabilite/exports/", {"type_export": "VENTES", "periode_debut": str(aujourd_hui), "periode_fin": str(aujourd_hui)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        contenu = api.get(f"/api/comptabilite/exports/{r.data['id']}/telecharger/").content.decode()
        lignes = contenu.strip().splitlines()
        self.assertEqual(lignes[0], "Journal;Date;Piece;Compte general;Compte tiers;Libelle;Debit;Credit")
        self.assertIn(f"VT;{aujourd_hui:%d/%m/%Y};{facture.numero};411;{self.client_evam.code}", contenu)
        self.assertIn(";1180,00;0,00", contenu)
        self.assertEqual(len(lignes), 4)


class NotificationsTests(BaseValidation):
    def test_decaissement_notifie_la_direction_puis_le_caissier(self):
        from apps.core.models import Notification
        session, api = self.ouvrir_caisse()
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        dg = Utilisateur.objects.create_user("dg", password="x", profil=Profil.DIRECTION)
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        Encaissement.objects.create(session_caisse=session, facture=facture, montant=500, mode_paiement="ESPECES")
        demande = api.post("/api/caisse/decaissements/", {"session_caisse": session.id, "montant": "80", "motif": "Carburant"}, format="json").data["id"]

        api_dg = APIClient()
        api_dg.force_authenticate(dg)
        self.assertEqual(api_dg.get("/api/notifications/non_lues/").data["non_lues"], 1)
        notif = api_dg.get("/api/notifications/").data["results"][0]
        self.assertEqual((notif["titre"], notif["type_document"], notif["document_id"]), ("Décaissement à autoriser", "caisse.decaissement", demande))
        self.assertTrue(Notification.objects.filter(destinataire=daf).exists())

        api_dg.post(f"/api/caisse/decaissements/{demande}/autoriser/")
        caissier_notifs = [n["titre"] for n in api.get("/api/notifications/").data["results"]]
        self.assertIn("Décaissement autorisé : à effectuer", caissier_notifs)
        self.assertFalse(Notification.objects.filter(destinataire=dg, titre__startswith="Décaissement autorisé").exists())  # pas l'auteur
        api_dg.post("/api/notifications/tout_lire/")
        self.assertEqual(api_dg.get("/api/notifications/non_lues/").data["non_lues"], 0)

    def test_notifications_personnelles(self):
        from apps.core.models import Notification
        autre = Utilisateur.objects.create_user("autre", password="x", profil=Profil.MAGASINIER)
        Notification.objects.create(destinataire=autre, titre="Pour autre")
        titres = [n["titre"] for n in self.api.get("/api/notifications/").data["results"]]
        self.assertNotIn("Pour autre", titres)
        self.assertIn("Fiche de composition à paramétrer", titres)   # la sienne (ADMIN_SI)


class AnomaliesTests(BaseValidation):
    def test_ecart_de_caisse_et_impaye(self):
        from apps.comptabilite.anomalies import detecter_anomalies
        from apps.comptabilite.models import AnomalieDetectee
        from apps.core.models import Notification
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        session, api = self.ouvrir_caisse()
        api.post(f"/api/caisse/sessions/{session.id}/cloturer/", {"solde_compte": "20", "justification": "Pièce trouvée"}, format="json")
        anomalie = AnomalieDetectee.objects.get(type_anomalie="ECART_CAISSE")
        self.assertIn("Écart de 20", anomalie.description)
        self.assertTrue(Notification.objects.filter(destinataire=daf, titre__startswith="Anomalie").exists())

        # Facture échue impayée : détectée une fois, puis résolue automatiquement après paiement.
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        Facture.objects.filter(pk=facture.pk).update(date_echeance="2020-01-01")
        self.assertEqual(detecter_anomalies()[0], 1)
        self.assertEqual(detecter_anomalies()[0], 0)                       # pas de doublon
        session2, api2 = self.ouvrir_caisse("Caisse 2")
        Encaissement.objects.create(session_caisse=session2, facture=facture, montant=facture.montant_total, mode_paiement="ESPECES")
        self.assertEqual(detecter_anomalies()[1], 1)
        self.assertEqual(AnomalieDetectee.objects.get(type_anomalie="IMPAYE").statut, "TRAITEE")

    def test_traitement_par_la_daf(self):
        from apps.comptabilite.anomalies import signaler_anomalie
        anomalie = signaler_anomalie("AUTRE", "Test", "Anomalie de test", cle="test-1")
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        api = APIClient()
        api.force_authenticate(daf)
        self.assert_refus(api.post("/api/comptabilite/anomalies/", {"type_anomalie": "AUTRE"}, format="json"))
        self.assert_refus(api.post(f"/api/comptabilite/anomalies/{anomalie.id}/ignorer/", {}, format="json"))
        r = api.post(f"/api/comptabilite/anomalies/{anomalie.id}/ignorer/", {"commentaire": "Cas connu"}, format="json")
        self.assertEqual((r.data["statut"], r.data["traite_par_nom"]), ("IGNOREE", "daf"))


class ValorisationTests(BaseValidation):
    def mouvement(self, type_mouvement, quantite, cout=None, depot="Magasin principal", article=None):
        return MouvementStock.objects.create(
            article=article or self.matiere, depot=depot_par_defaut(depot), type_mouvement=type_mouvement,
            quantite=quantite, cout_unitaire=cout, utilisateur=self.admin,
        )

    def test_cout_moyen_pondere(self):
        from apps.stocks.models import ValorisationArticle
        self.mouvement("ENTREE", 100, cout=10)                  # 100 x 10
        self.mouvement("ENTREE", 100, cout=20)                  # CMUP = (1000 + 2000) / 200 = 15
        self.assertEqual(ValorisationArticle.objects.get(article=self.matiere).cout_unitaire_moyen, Decimal("15"))
        sortie = self.mouvement("SORTIE", 50)
        self.assertEqual((sortie.cout_unitaire, sortie.valeur), (Decimal("15"), Decimal("750.00")))
        self.mouvement("ENTREE", 50, cout=27)                   # (150 x 15 + 50 x 27) / 200 = 18
        self.assertEqual(ValorisationArticle.objects.get(article=self.matiere).cout_unitaire_moyen, Decimal("18"))

        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        api = APIClient()
        api.force_authenticate(daf)
        r = api.get("/api/stocks/valorisation/")
        self.assertEqual(Decimal(r.data["valeur_totale"]), Decimal("3600.00"))   # 200 x 18
        responsable = Utilisateur.objects.create_user("rp", password="x", profil=Profil.RESPONSABLE_PRODUCTION)
        api.force_authenticate(responsable)
        self.assertEqual(api.get("/api/stocks/valorisation/").status_code, 403)   # donnée financière

    def test_cout_de_revient_de_l_of_et_entree_du_produit_fini(self):
        from apps.couts.models import CoutMainOeuvre, CoutReel
        from apps.production.models import SortieMatiere
        from apps.stocks.models import ValorisationArticle
        self.mouvement("ENTREE", 100, cout=5)                   # matière à 5 / kg
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        SortieMatiere.objects.create(ordre_fabrication=of, matiere=self.matiere, quantite_sortie=20)   # 100 de matières
        CoutMainOeuvre.objects.create(ordre_fabrication=of, heures=2, cout_horaire=25)                 # 50 de main-d'œuvre
        lot = Lot.objects.create(article=self.produit, ordre_fabrication=of, quantite=10, date_production="2026-09-01")
        Lot.objects.filter(pk=lot.pk).update(statut="CONFORME")
        lot.refresh_from_db()
        lot.liberer(self.admin)

        cout = CoutReel.objects.get(ordre_fabrication=of)
        self.assertEqual((cout.cout_matiere_total, cout.cout_main_oeuvre_total), (Decimal("100.00"), Decimal("50.00")))
        self.assertEqual(cout.cout_unitaire_reel, Decimal("15"))                   # 150 / 10 produits
        self.assertEqual(ValorisationArticle.objects.get(article=self.produit).cout_unitaire_moyen, Decimal("15"))

        facture = Facture.objects.create(commande=self.commande(statut="VALIDEE"))   # vendu 100 HT l'unité
        facture.generer_lignes_depuis_commande()
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        api = APIClient()
        api.force_authenticate(daf)
        r = api.get(f"/api/couts/couts-reels/{cout.id}/")
        self.assertEqual((Decimal(r.data["marge_unitaire"]), Decimal(r.data["taux_marge"])), (Decimal("85"), Decimal("85")))


class SeuilsControlesTests(BaseValidation):
    def test_la_daf_regle_les_seuils(self):
        from apps.caisse.models import Decaissement
        from apps.comptabilite.anomalies import detecter_anomalies
        from apps.comptabilite.models import AnomalieDetectee
        from apps.comptes.models import JournalAction
        from django.utils import timezone
        from datetime import timedelta
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF)
        api = APIClient()
        api.force_authenticate(daf)
        seuils = {s["cle"]: s for s in api.get("/api/comptabilite/seuils-controles/").data["results"]}
        self.assertEqual(Decimal(seuils["DELAI_DECAISSEMENT_EN_ATTENTE_JOURS"]["valeur"]), Decimal("2"))

        # Une demande de décaissement d'il y a 3 jours : alerte avec 2 jours, pas avec 5.
        session, api_caissier = self.ouvrir_caisse()
        demande = api_caissier.post("/api/caisse/decaissements/", {"session_caisse": session.id, "montant": "10", "motif": "x"}, format="json").data["id"]
        Decaissement.objects.filter(pk=demande).update(date_decaissement=timezone.now() - timedelta(days=3))
        url = f"/api/comptabilite/seuils-controles/{seuils['DELAI_DECAISSEMENT_EN_ATTENTE_JOURS']['id']}/"
        self.assertEqual(api.patch(url, {"valeur": "5"}, format="json").status_code, 200)
        detecter_anomalies()
        self.assertFalse(AnomalieDetectee.objects.filter(type_anomalie="DECAISSEMENT_EN_ATTENTE").exists())
        api.patch(url, {"valeur": "2"}, format="json")
        detecter_anomalies()
        self.assertTrue(AnomalieDetectee.objects.filter(type_anomalie="DECAISSEMENT_EN_ATTENTE").exists())

        self.assert_refus(api.patch(url, {"valeur": "2.5"}, format="json"))     # jours entiers
        self.assert_refus(api.patch(url, {"valeur": "500"}, format="json"))     # hors bornes
        self.assertEqual(JournalAction.objects.filter(
            document_type="comptabilite.parametrecontrole", action__startswith="Modification", utilisateur=daf,
        ).count(), 2)
        responsable = Utilisateur.objects.create_user("rp", password="x", profil=Profil.RESPONSABLE_PRODUCTION)
        api.force_authenticate(responsable)
        self.assertEqual(api.patch(url, {"valeur": "9"}, format="json").status_code, 403)


class JournalCompletTests(BaseValidation):
    def test_toutes_les_actions_sont_journalisees(self):
        from apps.comptes.models import JournalAction
        commercial = Utilisateur.objects.create_user("com", password="x", profil=Profil.COMMERCIAL)
        api = APIClient()
        api.force_authenticate(commercial)
        commande_id = api.post("/api/commercial/commandes/", {"client": self.client_evam.id, "type_commande": "COMPTANT"}, format="json").data["id"]
        ligne_id = api.post("/api/commercial/lignes-commande/", {"commande": commande_id, "article": self.produit.id, "quantite": "2", "prix_unitaire": "100"}, format="json").data["id"]
        api.patch(f"/api/commercial/lignes-commande/{ligne_id}/", {"quantite": "3"}, format="json")
        api.delete(f"/api/commercial/lignes-commande/{ligne_id}/")

        traces = JournalAction.objects.filter(utilisateur=commercial, document_type="commercial.lignecommande").order_by("pk")
        self.assertEqual([t.action.split(" :")[0] for t in traces], ["Création", "Modification", "Suppression"])
        modification = traces[1]
        self.assertEqual((modification.ancienne_valeur, modification.nouvelle_valeur), ("Quantité : 2.000", "Quantité : 3.000"))
        self.assertEqual(modification.requete, f"PATCH /api/commercial/lignes-commande/{ligne_id}/")
        self.assertEqual(modification.adresse_ip, "127.0.0.1")
        creation = JournalAction.objects.get(document_type="commercial.commande", action__startswith="Création")
        self.assertIn("Client : ", creation.nouvelle_valeur)
        self.assertIn("Client test", creation.nouvelle_valeur)
        self.assertEqual(creation.module, "COMMERCIAL")

    def test_connexions_et_mot_de_passe_masque(self):
        from apps.comptes.models import JournalAction
        Utilisateur.objects.create_user("awa", password="MotDePasse!2026", profil=Profil.CAISSIER)
        client = APIClient()
        self.assertEqual(client.post("/api/auth/connexion/", {"username": "awa", "password": "MotDePasse!2026"}, format="json").status_code, 200)
        self.assertEqual(client.post("/api/auth/connexion/", {"username": "awa", "password": "faux"}, format="json").status_code, 401)
        self.assertTrue(JournalAction.objects.filter(action="Connexion", utilisateur__username="awa").exists())
        self.assertTrue(JournalAction.objects.filter(action="Échec de connexion", nouvelle_valeur="Identifiant : awa").exists())
        creation = JournalAction.objects.get(document_type="comptes.utilisateur", document_id="awa", action__startswith="Création")
        self.assertIn("(masqué)", creation.nouvelle_valeur)
        self.assertNotIn("MotDePasse", creation.nouvelle_valeur)

    def test_consultation_du_journal(self):
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF, first_name="Awa", last_name="Kodia")
        api = APIClient()
        api.force_authenticate(daf)
        api.post("/api/comptabilite/anomalies/detecter/")
        self.api.post("/api/caisse/caisses/", {"nom": "Caisse Nord"}, format="json")
        lignes = api.get("/api/comptes/journal/?document_type=caisse.caisse").data["results"]
        self.assertEqual([(l["action"], l["utilisateur_nom"]) for l in lignes], [("Création : Caisse", "admin")])
        _, api_caissier = self.ouvrir_caisse()
        self.assertEqual(api_caissier.get("/api/comptes/journal/").status_code, 403)


class BesoinsMatieresAgentTests(BaseValidation):
    def test_agent_lit_les_besoins_de_ses_of_uniquement(self):
        agent = Utilisateur.objects.create_user("agent", password="x", profil=Profil.AGENT_PRODUCTION)
        api = APIClient()
        api.force_authenticate(agent)
        mon_of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=5, responsable=self.admin)
        mon_of.affecter_agents([agent], par=self.admin)

        r = api.get("/api/production/besoins-matieres/")
        self.assertEqual(r.status_code, 200, r.content)
        besoins = r.data["results"]
        self.assertEqual([b["ordre_fabrication"] for b in besoins], [mon_of.id])          # pas l'autre OF
        self.assertEqual((Decimal(besoins[0]["quantite_theorique"]), besoins[0]["situation"]), (Decimal("20"), "Insuffisant"))
        self.assertNotIn("cout", " ".join(besoins[0].keys()))                             # aucune donnée financière
        self.assertEqual(api.get(f"/api/production/besoins-matieres/?ordre_fabrication={mon_of.id}").data["count"], 1)
