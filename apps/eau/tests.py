from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from apps.comptes.models import Profil, Utilisateur
from apps.eau.models import (
    Bloc, CaracteristiquesEquipement, ParametresEau, Periode, bloc_de_l_equipement, coefficient_mensuel,
    montant_mensuel_etale, montant_mensuel_frequence, mois_courant, mois_suivant,
)
from apps.industriel.models import Activite, Equipement, EtapeStandard, Ligne, Poste, Usine

CENTIME = Decimal("0.01")


def mois_precedent(mois):
    annee, numero = (int(x) for x in mois.split("-"))
    return f"{annee - (numero == 1):04d}-{(numero - 2) % 12 + 1:02d}"


class BaseEau(TestCase):
    def setUp(self):
        self.usine = Usine.objects.create(nom="Site eau test")
        ligne = Ligne.objects.create(designation="Traitement", usine=self.usine, activite=Activite.objects.create(designation="Eau test"))
        etape = lambda code: EtapeStandard.objects.get(code=code)
        self.poste_captage = Poste.objects.create(ligne=ligne, etape=etape("CAPTAGE"))
        self.poste_uf = Poste.objects.create(ligne=ligne, etape=etape("ULTRAFILTRATION"))
        self.poste_remplissage = Poste.objects.create(
            ligne=ligne, etape=EtapeStandard.objects.get_or_create(code="REMPLISSAGE", defaults={"libelle": "Remplissage"})[0],
        )
        self.pompe_forage = Equipement.objects.create(designation="Pompe du forage", type_equipement="FORAGE", usine=self.usine, poste=self.poste_captage)
        self.pompe_uf = Equipement.objects.create(designation="Pompe UF", type_equipement="POMPE", usine=self.usine, poste=self.poste_uf)
        self.soutireuse = Equipement.objects.create(designation="Soutireuse", type_equipement="REMPLISSEUSE", usine=self.usine, poste=self.poste_remplissage)
        self.courant = mois_courant()
        self.suivant = mois_suivant(self.courant)
        self.passe = mois_precedent(self.courant)

    def client_pour(self, profil):
        utilisateur = Utilisateur.objects.filter(username=profil.lower()).first() \
            or Utilisateur.objects.create_user(profil.lower(), password="x", profil=profil)
        api = APIClient()
        api.force_authenticate(utilisateur)
        return api


class CalculsTests(BaseEau):
    """Formules de l'onglet « Calcul coût eau » (valeurs de test du classeur)."""

    def test_coefficients_des_periodes(self):
        self.assertEqual(coefficient_mensuel(Periode.MOIS), 1)
        self.assertEqual(round(coefficient_mensuel(Periode.JOUR), 4), Decimal("30.4167"))
        self.assertEqual(round(coefficient_mensuel(Periode.SEMAINE), 4), Decimal("4.3333"))
        self.assertEqual(round(coefficient_mensuel(Periode.AN), 6), Decimal("0.083333"))

    def test_montants_mensuels_du_classeur(self):
        cas = [
            (montant_mensuel_frequence(5, 100, 720, Periode.MOIS) * Decimal("0.4"), "144000.00"),  # électricité forage x part site 1
            (montant_mensuel_frequence(1, 120000, 3, Periode.AN) * Decimal("0.4"), "12000.00"),     # entretien pompe du forage
            (montant_mensuel_frequence(1, 10000, 1, Periode.SEMAINE), "43333.33"),                  # kits de contrôle interne
            (montant_mensuel_frequence(10, 3000, 4, Periode.AN), "10000.00"),                       # nettoyage de la cuve
            (montant_mensuel_frequence(50, 300, 4, Periode.MOIS), "60000.00"),                      # sel de régénération
            (montant_mensuel_etale(500, 400, 24), "8333.33"),                                       # sable
            (montant_mensuel_etale(1, 1000000, 48), "20833.33"),                                    # membrane DP1
            (montant_mensuel_etale(1, 12000000, 120) * Decimal("0.4"), "40000.00"),                 # amortissement forage
        ]
        for montant, attendu in cas:
            self.assertEqual(montant.quantize(CENTIME), Decimal(attendu))

    def test_bloc_deduit_de_l_etape(self):
        self.assertEqual(bloc_de_l_equipement(self.pompe_forage), Bloc.FORAGE)
        self.assertEqual(bloc_de_l_equipement(self.pompe_uf), Bloc.TRAITEMENT)
        self.assertIsNone(bloc_de_l_equipement(self.soutireuse))

    def test_etapes_du_classeur_installees_sous_le_traitement(self):
        for code in ("PREFILTRATION", "ULTRAFILTRATION", "CUVES_EAU", "CONTROLE_QUALITE_EAU"):
            etape = EtapeStandard.objects.get(code=code)
            self.assertEqual((etape.phase, etape.sous_etape_de.code), ("AMONT", "TRAITEMENT"))


class VersionsTests(BaseEau):
    """Aucun effet rétroactif : une modification ne vaut qu'à partir du mois suivant."""

    def parametres(self, mois, **champs):
        return ParametresEau.objects.create(usine=self.usine, mois_application=mois, **champs)

    def test_premiere_version_sur_un_mois_passe_corrigeable_tant_qu_elle_est_seule(self):
        initiale = self.parametres(self.passe, taux_rejet_tolere_pct=2)
        initiale.taux_rejet_tolere_pct = 3
        initiale.save()
        self.assertFalse(initiale.figee)

    def test_nouvelle_version_au_plus_tot_le_mois_suivant_puis_ancienne_figee(self):
        initiale = self.parametres(self.passe)
        for mois in (self.passe, self.courant):
            with self.assertRaises(ValidationError):
                self.parametres(mois, seuil_ecart_standard_pct=4)
        nouvelle = self.parametres(self.suivant, seuil_ecart_standard_pct=4)
        initiale.refresh_from_db()
        self.assertTrue(initiale.figee)
        initiale.seuil_ecart_standard_pct = 6
        with self.assertRaises(ValidationError):
            initiale.save()
        with self.assertRaises(ValidationError):
            initiale.delete()
        # La version future reste modifiable et supprimable.
        nouvelle.seuil_ecart_standard_pct = 3
        nouvelle.save()
        nouvelle.delete()

    def test_version_en_vigueur_selon_le_mois(self):
        self.parametres(self.passe, seuil_ecart_standard_pct=5)
        self.parametres(self.suivant, seuil_ecart_standard_pct=4)
        en_vigueur = lambda mois: ParametresEau.en_vigueur(mois, usine=self.usine).seuil_ecart_standard_pct
        self.assertEqual(en_vigueur(self.courant), 5)
        self.assertEqual(en_vigueur(self.suivant), 4)
        self.assertEqual(en_vigueur(mois_suivant(self.suivant)), 4)
        self.assertIsNone(ParametresEau.en_vigueur(mois_precedent(self.passe), usine=self.usine))

    def test_controles_des_valeurs(self):
        for champs in ({"seuil_ecart_standard_pct": 120}, {"jour_cloture": 31}, {"seuil_grosse_reparation": -1}):
            with self.assertRaises(ValidationError):
                self.parametres(self.passe, **champs)
        with self.assertRaises(ValidationError):
            self.parametres("2026-13")

    def test_caracteristiques_versionnees_par_equipement(self):
        CaracteristiquesEquipement.objects.create(equipement=self.pompe_forage, mois_application=self.passe, puissance_kw=5, heures_marche_jour=24)
        # Un autre équipement a sa propre première version.
        CaracteristiquesEquipement.objects.create(equipement=self.pompe_uf, mois_application=self.passe, puissance_kw=3)
        with self.assertRaises(ValidationError):
            CaracteristiquesEquipement.objects.create(equipement=self.pompe_forage, mois_application=self.courant, puissance_kw=6)
        for champs in ({}, {"heures_marche_jour": 25}, {"puissance_kw": 0}):
            with self.assertRaises(ValidationError):
                CaracteristiquesEquipement.objects.create(equipement=self.soutireuse, mois_application=self.passe, **champs)


class ApiTests(BaseEau):
    """Rôles et droits du classeur."""

    def test_seul_le_controle_de_gestion_parametre(self):
        donnees = {"usine": self.usine.pk, "mois_application": self.passe, "taux_rejet_tolere_pct": "2"}
        for profil in (Profil.COMPTABILITE_DAF, Profil.TECHNICIEN_EAU, Profil.ADMIN_SI):
            self.assertEqual(self.client_pour(profil).post("/api/eau/parametres/", donnees, format="json").status_code, 403)
        controle = self.client_pour(Profil.CONTROLE_GESTION)
        reponse = controle.post("/api/eau/parametres/", donnees, format="json")
        self.assertEqual(reponse.status_code, 201, reponse.content)
        self.assertEqual(reponse.data["saisi_par_nom"], "controle_gestion")
        # Modification rétroactive refusée avec un message clair.
        refus = controle.post("/api/eau/parametres/", {**donnees, "mois_application": self.courant}, format="json")
        self.assertEqual(refus.status_code, 400)
        self.assertIn("mois_application", refus.data)
        reponse = controle.get(f"/api/eau/parametres/en_vigueur/?usine={self.usine.pk}&mois={self.courant}")
        self.assertEqual(reponse.data["taux_rejet_tolere_pct"], "2.00")
        self.assertEqual(self.client_pour(Profil.COMPTABILITE_DAF).get("/api/eau/parametres/").status_code, 200)

    def test_le_technicien_voit_les_donnees_techniques_mais_pas_les_seuils(self):
        CaracteristiquesEquipement.objects.create(equipement=self.pompe_forage, mois_application=self.passe, puissance_kw=5, heures_marche_jour=24)
        CaracteristiquesEquipement.objects.create(equipement=self.pompe_forage, mois_application=self.suivant, puissance_kw=6, heures_marche_jour=24)
        technicien = self.client_pour(Profil.TECHNICIEN_EAU)
        self.assertEqual(technicien.get("/api/eau/parametres/").status_code, 403)
        reponse = technicien.get(f"/api/eau/caracteristiques-equipements/en_vigueur/?usine={self.usine.pk}&mois={self.courant}")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual([(l["equipement_code"], l["puissance_kw"], l["bloc"]) for l in reponse.data],
                         [(self.pompe_forage.code, "5.000", "FORAGE")])
        self.assertEqual(technicien.post("/api/eau/caracteristiques-equipements/", {
            "equipement": self.pompe_uf.pk, "mois_application": self.passe, "puissance_kw": "3"}, format="json").status_code, 403)
        listes = technicien.get("/api/eau/listes/").data
        self.assertEqual([p["coefficient"] for p in listes["periodes"]], ["365/12", "52/12", "1/1", "1/12"])
        self.assertEqual(len(listes["familles"]), 4)

    def test_le_controle_de_gestion_parametre_les_equipements(self):
        reponse = self.client_pour(Profil.CONTROLE_GESTION).patch(
            f"/api/industriel/equipements/{self.pompe_uf.pk}/", {"designation": "Pompe de l'ultrafiltration"}, format="json",
        )
        self.assertEqual(reponse.status_code, 200, reponse.content)
