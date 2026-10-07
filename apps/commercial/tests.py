"""
Tests des ventes selon les réponses du client (questionnaire, Q68, Q70,
Q73) : devis, tarif imposé, tarifs par client et par contrat, dérogation
tracée, circuit des clients sous contrat.

Lancer : python manage.py test apps.commercial
"""

from datetime import date, timedelta
from decimal import Decimal

from rest_framework.test import APIClient

from apps.commercial.models import Commande, ContratClient, Devis, LigneCommande, LigneDevis, Tarif
from apps.comptes.models import Profil, Utilisateur
from apps.core.tests import BaseValidation


def api_pour(profil, nom):
    api = APIClient()
    api.force_authenticate(Utilisateur.objects.create_user(nom, password="x", profil=profil))
    return api


class TarifImposeTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.contrat = ContratClient.objects.create(client=self.client_evam, date_debut=date.today() - timedelta(days=30))
        self.commercial = api_pour(Profil.COMMERCIAL, "com")

    def test_prix_repris_du_tarif_et_impose_au_comptant(self):
        commande = self.commande(lignes=())
        r = self.commercial.post("/api/commercial/lignes-commande/", {"commande": commande.id, "article": self.produit.id, "quantite": 3}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Decimal(r.data["prix_unitaire"]), Decimal(100))
        refus = self.assert_refus(self.commercial.post("/api/commercial/lignes-commande/", {
            "commande": commande.id, "article": self.produit.id, "quantite": 1, "prix_unitaire": "90",
        }, format="json"))
        self.assertIn("imposé", str(refus.data))

    def test_tarif_contrat_puis_client_puis_public(self):
        Tarif.objects.create(article=self.produit, client=self.client_evam, prix_unitaire=95, date_debut_validite=date(2020, 1, 1))
        self.assertEqual(Tarif.applicable(self.produit, self.client_evam).prix_unitaire, 95)
        Tarif.objects.create(article=self.produit, contrat=self.contrat, prix_unitaire=90, date_debut_validite=date(2020, 1, 1))
        self.assertEqual(Tarif.applicable(self.produit, self.client_evam).prix_unitaire, 90)
        autre = self.client_evam.__class__.objects.create(nom="Particulier", type_client="PARTICULIER", encours_autorise=0)
        self.assertEqual(Tarif.applicable(self.produit, autre).prix_unitaire, 100)

    def test_derogation_contrat_autorisee_par_la_direction_seulement(self):
        commande = Commande.objects.create(client=self.client_evam, type_commande="CONTRAT", cree_par=self.admin)
        ligne = LigneCommande.objects.create(commande=commande, article=self.produit, quantite=10)
        refus = self.commercial.post(f"/api/commercial/lignes-commande/{ligne.id}/autoriser_prix/", {"prix_unitaire": "85", "motif": "Volume"}, format="json")
        self.assertEqual(refus.status_code, 403)
        direction = api_pour(Profil.DIRECTION, "dg")
        self.assert_refus(direction.post(f"/api/commercial/lignes-commande/{ligne.id}/autoriser_prix/", {"prix_unitaire": "85"}, format="json"))
        ok = direction.post(f"/api/commercial/lignes-commande/{ligne.id}/autoriser_prix/", {"prix_unitaire": "85", "motif": "Remise volume"}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        ligne.refresh_from_db()
        self.assertEqual((ligne.prix_unitaire, ligne.prix_tarif, ligne.derogation_autorisee_par.username), (Decimal(85), Decimal(100), "dg"))

    def test_article_sans_tarif_refuse(self):
        sans_tarif = self.nouveau_pf(format="150 cl")
        commande = self.commande(lignes=())
        refus = self.assert_refus(self.api.post("/api/commercial/lignes-commande/", {"commande": commande.id, "article": sans_tarif.id, "quantite": 1}, format="json"))
        self.assertIn("Aucun tarif", str(refus.data))

    def test_commande_contrat_sans_contrat_refusee(self):
        sans_contrat = self.client_evam.__class__.objects.create(nom="Sans contrat", type_client="SOCIETE", encours_autorise=1000)
        self.assert_refus(self.api.post("/api/commercial/commandes/", {"client": sans_contrat.id, "type_commande": "CONTRAT"}, format="json"))


class DevisTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.devis = Devis.objects.create(client=self.client_evam, date_validite=date.today() + timedelta(days=15), cree_par=self.admin)
        self.ligne = LigneDevis.objects.create(devis=self.devis, article=self.produit, quantite=50)

    def test_circuit_complet_avec_acceptation_partielle(self):
        self.assertEqual(self.ligne.prix_unitaire, Decimal(100))
        self.assertEqual(self.api.post(f"/api/commercial/devis/{self.devis.id}/envoyer/").status_code, 200)
        self.assert_refus(self.api.post("/api/commercial/lignes-devis/", {"devis": self.devis.id, "article": self.produit.id, "quantite": 1}, format="json"))
        r = self.api.post(f"/api/commercial/devis/{self.devis.id}/accepter/", {"quantites": {str(self.ligne.id): 30}}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["devis"]["statut"], "PARTIELLEMENT_ACCEPTE")
        commande = Commande.objects.get(devis=self.devis)
        self.assertEqual(commande.lignes.get().quantite, Decimal(30))
        self.assert_refus(self.api.post(f"/api/commercial/devis/{self.devis.id}/accepter/"))   # déjà accepté
        pdf = self.api.get(f"/api/commercial/devis/{self.devis.id}/pdf/")
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_revision_refus_et_expiration(self):
        self.devis.envoyer()
        self.assertEqual(self.api.post(f"/api/commercial/devis/{self.devis.id}/reviser/").data["statut"], "BROUILLON")
        self.devis.refresh_from_db()
        self.devis.envoyer()
        Devis.objects.filter(pk=self.devis.pk).update(date_validite=date.today() - timedelta(days=1))
        refus = self.assert_refus(self.api.post(f"/api/commercial/devis/{self.devis.id}/accepter/"))
        self.assertIn("expiré", str(refus.data))
        self.devis.refresh_from_db()
        self.assertEqual(self.devis.statut, "EXPIRE")
        self.assertFalse(Commande.objects.filter(devis=self.devis).exists())

    def test_refus_motive(self):
        self.devis.envoyer()
        r = self.api.post(f"/api/commercial/devis/{self.devis.id}/refuser/", {"motif": "Prix trop élevé"}, format="json")
        self.assertEqual((r.data["statut"], r.data["motif_refus"]), ("REFUSE", "Prix trop élevé"))
