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
        self.assertEqual(api_a.get(f"/api/caisse/caisses/{session_b.caisse_id}/journal/").status_code, 403)
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
    def test_autorise_par_direction_ou_daf_uniquement(self):
        session, api = self.ouvrir_caisse()
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        Encaissement.objects.create(session_caisse=session, facture=facture, montant=500, mode_paiement="ESPECES")
        daf = Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF, first_name="Awa", last_name="Kodia")
        Utilisateur.objects.create_user("dg", password="x", profil=Profil.DIRECTION)
        Utilisateur.objects.create_user("dg_parti", password="x", profil=Profil.DIRECTION, is_active=False)
        commercial = Utilisateur.objects.create_user("com", password="x", profil=Profil.COMMERCIAL)

        liste = api.get("/api/caisse/decaissements/autorisateurs/").data
        self.assertEqual({p["username"] for p in liste}, {"daf", "dg"})
        self.assertIn("Awa Kodia", {p["nom"] for p in liste})

        donnees = {"session_caisse": session.id, "montant": "100", "motif": "Achat fournitures"}
        self.assert_refus(api.post("/api/caisse/decaissements/", {**donnees, "autorise_par": commercial.id}, format="json"))
        r = api.post("/api/caisse/decaissements/", {**donnees, "autorise_par": daf.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["autorise_par_nom"], "Awa Kodia")
