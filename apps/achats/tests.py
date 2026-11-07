from django.test import TestCase
from rest_framework.test import APIClient

from apps.achats.models import DemandeAchat, StatutDemandeAchat
from apps.comptes.models import Profil, Utilisateur
from apps.referentiel.models import Article


class TraitementDemandeAchatTests(TestCase):
    """Qui peut approuver / rejeter une demande d'achat."""

    def setUp(self):
        self.article = Article.objects.create(type_article="MATIERE_PREMIERE", unite_mesure="UNITE")
        self.demandeur = Utilisateur.objects.create_user("prod", password="x", profil=Profil.RESPONSABLE_PRODUCTION)

    def demande(self):
        return DemandeAchat.objects.create(article=self.article, quantite_demandee=10, demandeur=self.demandeur)

    def client_pour(self, profil):
        api = APIClient()
        api.force_authenticate(Utilisateur.objects.create_user(profil.lower(), password="x", profil=profil))
        return api

    def test_admin_si_peut_approuver_et_rejeter(self):
        api = self.client_pour(Profil.ADMIN_SI)
        a_approuver, a_rejeter = self.demande(), self.demande()
        r = api.post(f"/api/achats/demandes/{a_approuver.id}/approuver/")
        self.assertEqual((r.status_code, r.data["statut"]), (200, StatutDemandeAchat.APPROUVEE), r.content)
        r = api.post(f"/api/achats/demandes/{a_rejeter.id}/rejeter/")
        self.assertEqual((r.status_code, r.data["statut"]), (200, StatutDemandeAchat.REJETEE), r.content)

    def test_responsable_achats_peut_approuver(self):
        r = self.client_pour(Profil.RESPONSABLE_ACHATS).post(f"/api/achats/demandes/{self.demande().id}/approuver/")
        self.assertEqual(r.status_code, 200, r.content)

    def test_demandeur_ne_peut_pas_approuver_sa_propre_demande(self):
        for profil in (Profil.RESPONSABLE_PRODUCTION, Profil.MAGASINIER):
            demande = self.demande()
            r = self.client_pour(profil).post(f"/api/achats/demandes/{demande.id}/approuver/")
            self.assertEqual(r.status_code, 403, profil)
            demande.refresh_from_db()
            self.assertEqual(demande.statut, StatutDemandeAchat.EN_ATTENTE)
