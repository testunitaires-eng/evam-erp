from django.test import TestCase
from rest_framework.test import APIClient

from apps.comptes.models import Profil, Utilisateur


class TransfertsDepotsTests(TestCase):
    """Les dépôts et transferts passent uniquement par le module stocks."""

    def test_anciennes_routes_distribution_supprimees(self):
        api = APIClient()
        api.force_authenticate(Utilisateur.objects.create_user("admin_si", password="x", profil=Profil.ADMIN_SI))
        self.assertEqual(api.get("/api/distribution/depots/").status_code, 404)
        self.assertEqual(api.get("/api/distribution/transferts/").status_code, 404)
        self.assertEqual(api.get("/api/stocks/depots/").status_code, 200)
        self.assertEqual(api.get("/api/stocks/transferts/").status_code, 200)
