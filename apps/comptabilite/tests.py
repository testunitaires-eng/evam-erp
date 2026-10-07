"""
Tests comptables selon les réponses du client (Q63, Q65, Q67) : comptes
702x paramétrables, synthèse de caisse des ventes comptoir, export
générique, préparation SFEC.

Lancer : python manage.py test apps.comptabilite
"""

import json
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

from apps.caisse.models import Encaissement
from apps.commercial.models import Client, Commande, Facture, LigneCommande
from apps.comptabilite.ecritures import ecritures_de
from apps.comptabilite.models import EcritureComptable, RegleCompte
from apps.comptes.models import Profil, Utilisateur
from apps.core.models import ParametreEntreprise
from apps.core.tests import BaseValidation
from apps.fiscalite import sfec


class ComptesParametresTests(BaseValidation):
    def test_sous_compte_par_format_plus_precis_que_l_activite(self):
        r = self.api.post("/api/comptabilite/regles-comptes/", {
            "sens": "VENTE", "compte": "702011", "libelle": "Eau 70 cl Pack de 8",
            "format": self.produit.format_id, "unite_vente": self.produit.unite_vente_id,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        simulation = self.api.get("/api/comptabilite/regles-comptes/simuler/", {"article": self.produit.id}).data
        self.assertEqual(simulation["compte_vente"], "702011")
        self.assertEqual(simulation["compte_achat"], "602")    # 602 par défaut (pas une matière)
        self.assertEqual(self.api.get("/api/comptabilite/regles-comptes/simuler/", {"article": self.matiere.id}).data["compte_achat"], "602")
        self.assert_refus(self.api.post("/api/comptabilite/regles-comptes/", {"sens": "VENTE", "compte": "601", "type_article": "PRODUIT_FINI"}, format="json"))


class SyntheseCaisseTests(BaseValidation):
    def test_ventes_comptoir_en_une_ecriture_de_synthese(self):
        particulier = Client.objects.create(nom="Comptoir", type_client="PARTICULIER", encours_autorise=10**6)
        session, api_caissier = self.ouvrir_caisse()
        factures = []
        for quantite in (3, 2):
            commande = Commande.objects.create(client=particulier, type_commande="COMPTANT", cree_par=self.admin)
            LigneCommande.objects.create(commande=commande, article=self.produit, quantite=quantite)
            commande.statut = "VALIDEE"
            commande.save()
            facture = Facture.objects.create(commande=commande)
            facture.generer_lignes_depuis_commande()
            facture.refresh_from_db()
            Encaissement.objects.create(session_caisse=session, facture=facture, montant=facture.montant_total, mode_paiement="ESPECES")
            factures.append(facture)
        self.assertFalse(ecritures_de(factures[0]).exists())   # pas de compte client individuel
        session.cloturer(solde_compte=session.calculer_solde_theorique())
        ecriture = ecritures_de(session).get()
        lignes = {(l.compte, l.debit, l.credit) for l in ecriture.lignes.all()}
        self.assertEqual(lignes, {("571", Decimal("590.00"), Decimal("0")), ("7020", Decimal("0"), Decimal("500.00")),
                                  ("4431", Decimal("0"), Decimal("90.00"))})


class ExportGeneriqueTests(BaseValidation):
    def test_csv_json_excel(self):
        facture = Facture.objects.create(commande=self.commande(statut="VALIDEE"))
        facture.generer_lignes_depuis_commande()
        daf = APIClient()
        daf.force_authenticate(Utilisateur.objects.create_user("daf", password="x", profil=Profil.COMPTABILITE_DAF))
        jour = str(timezone.localdate())
        for format_fichier, verification in (
            ("CSV_GENERIQUE", lambda c: c.decode("utf-8-sig").splitlines()[0] == "journal;date;numero_ecriture;piece;compte;compte_tiers;libelle;debit;credit"),
            ("JSON", lambda c: len(json.loads(c)["lignes"]) == 3),
            ("XLSX", lambda c: c.startswith(b"PK")),
        ):
            export = daf.post("/api/comptabilite/exports/", {"type_export": "VENTES", "format_fichier": format_fichier,
                                                             "periode_debut": jour, "periode_fin": jour}, format="json")
            self.assertEqual(export.status_code, 201, export.content)
            contenu = daf.get(f"/api/comptabilite/exports/{export.data['id']}/telecharger/").content
            self.assertTrue(verification(contenu), format_fichier)


class SfecTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.facture = Facture.objects.create(commande=self.commande(statut="VALIDEE"))
        self.facture.generer_lignes_depuis_commande()

    def test_donnees_pretes_et_certification_refusee_tant_que_non_activee(self):
        r = self.api.get(f"/api/commercial/factures/{self.facture.id}/sfec/").data
        self.assertEqual(r["statut"], "EN_ATTENTE")
        self.assertEqual(r["donnees"]["articles"][0]["code"], self.produit.code)
        self.assertEqual(r["donnees"]["totaux"]["ttc"], "1180.00")
        refus = self.assert_refus(self.api.post(f"/api/commercial/factures/{self.facture.id}/sfec/"))
        self.assertIn("pas encore activée", str(refus.data))

    def test_erreur_tracee_puis_certification_imprimee(self):
        ParametreEntreprise.objects.update_or_create(pk=1, defaults={"sfec_actif": True})
        self.assert_refus(self.api.post(f"/api/commercial/factures/{self.facture.id}/sfec/"))
        self.facture.refresh_from_db()
        self.assertEqual(self.facture.sfec_statut, "ERREUR")
        sfec.enregistrer_certification(self.facture, code="TEST-ABCD-1234", qr="F;TEST;1180", compteurs="12/12 FV", nim="ED01000001")
        pdf = self.api.get(f"/api/commercial/factures/{self.facture.id}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
