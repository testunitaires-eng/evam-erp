"""
Tests des documents imprimés en PDF (facture, avoir, bon de livraison,
bon de commande fournisseur, reçu de caisse, bon de sortie, bon de
transfert) et du paramétrage de l'entreprise (identité, logo).

Lancer : python manage.py test apps.core.tests_documents
"""

from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.achats.models import CommandeFournisseur, Fournisseur, LigneCommandeFournisseur
from apps.caisse.models import Encaissement
from apps.commercial.models import Avoir, Facture
from apps.comptes.models import Profil, Utilisateur
from apps.distribution.models import BonLivraison, PreparationLivraison
from apps.production.models import OrdreFabrication
from apps.stocks.models import Depot, LigneTransfert, TransfertStock, depot_par_defaut

from .models import ParametreEntreprise
from .pdf import en_lettres, montant_en_lettres, nombre
from .tests import BaseValidation


def image_png():
    tampon = BytesIO()
    Image.new("RGB", (200, 100), "#0A6676").save(tampon, "PNG")
    return tampon.getvalue()


class MontantEnLettresTests(BaseValidation):
    def test_nombres_en_lettres(self):
        self.assertEqual(en_lettres(71), "soixante et onze")
        self.assertEqual(en_lettres(80), "quatre-vingts")
        self.assertEqual(en_lettres(80000), "quatre-vingt mille")
        self.assertEqual(en_lettres(200), "deux cents")
        self.assertEqual(en_lettres(201), "deux cent un")
        self.assertEqual(en_lettres(1000), "mille")
        self.assertEqual(en_lettres(2_000_000), "deux millions")
        self.assertEqual(en_lettres(310_635), "trois cent dix mille six cent trente-cinq")
        self.assertEqual(montant_en_lettres("1500.50"), "Mille cinq cents francs CFA et cinquante centimes")
        self.assertEqual(nombre(1234567), "1\xa0234\xa0567")


class DocumentsPdfTests(BaseValidation):
    def setUp(self):
        super().setUp()
        entreprise = ParametreEntreprise.courant()
        entreprise.ifu, entreprise.rccm, entreprise.logo, entreprise.logo_type = "3201912345678", "RB/COT/19 B 1", image_png(), "image/png"
        entreprise.save()

    def assert_pdf(self, url, nom):
        reponse = self.api.get(url)
        self.assertEqual(reponse.status_code, 200, getattr(reponse, "content", b"")[:300])
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertIn(nom, reponse["Content-Disposition"])
        contenu = b"".join(reponse.streaming_content) if reponse.streaming else reponse.content
        self.assertTrue(contenu.startswith(b"%PDF"))
        return contenu

    def facture_payee(self):
        self.entree_stock(self.produit, 100, depot="Dépôt produits finis")
        commande = self.commande(statut="VALIDEE")
        facture = Facture.objects.create(commande=commande)
        facture.generer_lignes_depuis_commande()
        facture.refresh_from_db()
        return commande, facture

    def test_facture_avoir_et_recu(self):
        commande, facture = self.facture_payee()
        self.assert_pdf(f"/api/commercial/factures/{facture.id}/pdf/", f"facture-{facture.numero}")
        session, _ = self.ouvrir_caisse("Caisse PDF")
        encaissement = Encaissement.objects.create(session_caisse=session, facture=facture, montant=500, mode_paiement="ESPECES")
        self.assert_pdf(f"/api/caisse/encaissements/{encaissement.id}/pdf/", f"recu-{encaissement.numero}")
        avoir = Avoir.objects.create(client=self.client_evam, facture_origine=facture, montant=100, motif="Casse", cree_par=self.admin)
        self.assert_pdf(f"/api/commercial/avoirs/{avoir.id}/pdf/", f"avoir-{avoir.numero}")
        telecharge = self.api.get(f"/api/commercial/factures/{facture.id}/pdf/?telecharger=1")
        self.assertTrue(telecharge["Content-Disposition"].startswith("attachment"))

    def test_bon_de_livraison(self):
        commande, _ = self.facture_payee()
        preparation = PreparationLivraison.objects.create(commande=commande, lancee_par=self.admin)
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_preparation/")
        self.api.post(f"/api/distribution/preparations/{preparation.id}/confirmer_sortie/")
        bon = BonLivraison.objects.create(commande=commande)
        self.assert_pdf(f"/api/distribution/bons-livraison/{bon.id}/pdf/", f"bon-livraison-{bon.numero}")

    def test_bon_de_commande_fournisseur(self):
        commande = CommandeFournisseur.objects.create(
            fournisseur=Fournisseur.objects.create(code="F1", nom="Sucrerie du Bénin", ifu="12345"), cree_par=self.admin,
        )
        LigneCommandeFournisseur.objects.create(commande=commande, article=self.matiere, quantite_commandee=250, prix_unitaire=650)
        self.assert_pdf(f"/api/achats/commandes/{commande.id}/pdf/", f"bon-commande-{commande.numero}")

    def test_bon_de_sortie_et_bon_de_transfert(self):
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=10, responsable=self.admin)
        self.assert_pdf(f"/api/production/ordres-fabrication/{of.id}/bon-de-sortie-pdf/", f"bon-sortie-{of.numero}")
        self.entree_stock(self.produit, 30, depot="Dépôt produits finis")
        transfert = TransfertStock.objects.create(
            depot_source=depot_par_defaut("Dépôt produits finis"),
            depot_destination=Depot.objects.create(nom="Dépôt Nord", type_lieu="DEPOT_EXTERIEUR"), cree_par=self.admin,
        )
        LigneTransfert.objects.create(transfert=transfert, article=self.produit, quantite=12)
        self.assert_pdf(f"/api/stocks/transferts/{transfert.id}/pdf/", f"bon-transfert-{transfert.numero}")

    def test_droits_d_acces_respectes(self):
        """Un profil qui ne voit pas la facture n'obtient pas son PDF."""
        _, facture = self.facture_payee()
        magasinier = Utilisateur.objects.create_user("mag", password="x", profil=Profil.MAGASINIER)
        api = APIClient()
        api.force_authenticate(magasinier)
        self.assertEqual(api.get(f"/api/commercial/factures/{facture.id}/pdf/").status_code, 403)

    def test_document_sans_logo(self):
        ParametreEntreprise.objects.filter(pk=1).update(logo=None)
        _, facture = self.facture_payee()
        self.assert_pdf(f"/api/commercial/factures/{facture.id}/pdf/", "facture")


class ParametreEntrepriseTests(BaseValidation):
    def test_identite_et_logo(self):
        r = self.api.patch("/api/documents/entreprise/", {"raison_sociale": "EVAM SARL", "ifu": "3201912345678"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(ParametreEntreprise.courant().ifu, "3201912345678")
        envoi = self.api.post("/api/documents/entreprise/logo/", {
            "logo": SimpleUploadedFile("logo.png", image_png(), content_type="image/png"),
        }, format="multipart")
        self.assertEqual(envoi.status_code, 200, envoi.content)
        self.assertTrue(envoi.data["a_un_logo"])
        self.assertEqual(self.api.get("/api/documents/entreprise/logo/")["Content-Type"], "image/png")
        self.assertEqual(self.api.get("/api/documents/apercu/").status_code, 200)

    def test_logo_invalide_et_couleur_refuses(self):
        r = self.api.post("/api/documents/entreprise/logo/", {
            "logo": SimpleUploadedFile("logo.png", b"pas une image", content_type="image/png"),
        }, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(ParametreEntreprise.courant().logo)
        self.assert_refus(self.api.patch("/api/documents/entreprise/", {"couleur": "bleu"}, format="json"))

    def test_seuls_les_profils_autorises_modifient(self):
        commercial = Utilisateur.objects.create_user("com", password="x", profil=Profil.COMMERCIAL)
        api = APIClient()
        api.force_authenticate(commercial)
        self.assertEqual(api.get("/api/documents/entreprise/").status_code, 200)
        self.assertEqual(api.patch("/api/documents/entreprise/", {"raison_sociale": "X"}, format="json").status_code, 403)
