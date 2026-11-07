from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.comptes.models import Profil, Utilisateur
from apps.core.tests import BaseValidation
from apps.industriel.models import Activite, EtapeStandard, Ligne, Poste, Usine
from apps.production.models import OrdreFabrication
from apps.personnel.models import Affectation, Ouvrier

AUJOURDHUI = timezone.localdate()


class PersonnelTests(BaseValidation):
    def setUp(self):
        super().setUp()
        self.remplissage = EtapeStandard.objects.get_or_create(code="REMPLISSAGE", defaults={"libelle": "Remplissage"})[0]
        self.nettoyage = EtapeStandard.objects.get_or_create(code="NETTOYAGE_TEST", defaults={"libelle": "Nettoyage test"})[0]
        usine = Usine.objects.create(nom="Usine test")
        self.ligne = Ligne.objects.create(designation="Ligne Eau 1", usine=usine, activite=Activite.objects.create(designation="Eau test"))
        self.poste = Poste.objects.create(ligne=self.ligne, etape=self.remplissage)

    def ouvrier(self, type_contrat="PERMANENT", fin=None, competences=None, **autres):
        ouvrier = Ouvrier.objects.create(
            nom="Mabiala", prenom="Jean", type_contrat=type_contrat,
            date_entree=autres.pop("entree", AUJOURDHUI - timedelta(days=30)), date_fin_contrat=fin, **autres,
        )
        ouvrier.competences.set(competences if competences is not None else [self.remplissage])
        return ouvrier

    def affecter(self, ouvrier, **champs):
        champs.setdefault("etape", self.remplissage)
        champs.setdefault("date_debut", AUJOURDHUI)
        return Affectation.objects.create(ouvrier=ouvrier, **champs)

    # -- registre -------------------------------------------------------------
    def test_creation_api_matricule_automatique_et_temporaire_sans_fin_refuse(self):
        donnees = {"nom": "Nkounkou", "prenom": "Marie", "type_contrat": "TEMPORAIRE", "date_entree": str(AUJOURDHUI),
                   "competences": [self.remplissage.id]}
        r = self.assert_refus(self.api.post("/api/personnel/ouvriers/", donnees, format="json"))
        self.assertIn("date_fin_contrat", r.data)
        donnees["date_fin_contrat"] = str(AUJOURDHUI + timedelta(days=60))
        r = self.api.post("/api/personnel/ouvriers/", donnees, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.data["matricule"].startswith("OUV-"))
        self.assertEqual((r.data["nom"], r.data["competences_libelles"], r.data["sous_contrat"]), ("NKOUNKOU", [self.remplissage.libelle], True))

    def test_meme_piece_d_identite_refusee(self):
        self.ouvrier(type_piece="CNI", numero_piece="AB123")
        with self.assertRaises(ValidationError):
            self.ouvrier(type_piece="CNI", numero_piece="ab123")

    # -- affectations ---------------------------------------------------------
    def test_affectation_hors_competence_refusee(self):
        ouvrier = self.ouvrier()
        with self.assertRaisesMessage(ValidationError, "zones de compétence"):
            self.affecter(ouvrier, etape=self.nettoyage)
        self.affecter(ouvrier)

    def test_temporaire_limite_a_son_contrat(self):
        fin = AUJOURDHUI + timedelta(days=10)
        ouvrier = self.ouvrier("TEMPORAIRE", fin=fin)
        self.assertEqual(self.affecter(ouvrier).date_fin, fin)                        # fin reprise du contrat
        Affectation.objects.all().delete()
        with self.assertRaisesMessage(ValidationError, "se termine le"):
            self.affecter(ouvrier, date_fin=fin + timedelta(days=1))
        with self.assertRaisesMessage(ValidationError, "n'entre chez EVAM"):
            self.affecter(ouvrier, date_debut=ouvrier.date_entree - timedelta(days=1), date_fin=fin)
        ouvrier.date_fin_contrat = AUJOURDHUI - timedelta(days=1)
        ouvrier.save()
        self.assertFalse(ouvrier.est_sous_contrat())

    def test_pas_deux_postes_en_meme_temps_mais_plusieurs_of(self):
        ouvrier = self.ouvrier()
        self.affecter(ouvrier, date_fin=AUJOURDHUI + timedelta(days=5))
        with self.assertRaisesMessage(ValidationError, "déjà affecté"):
            self.affecter(ouvrier, date_debut=AUJOURDHUI + timedelta(days=5))
        self.affecter(ouvrier, date_debut=AUJOURDHUI + timedelta(days=6))           # après : accepté
        of1 = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin, date_prevue=AUJOURDHUI)
        of2 = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        a1 = Affectation.objects.create(ouvrier=ouvrier, etape=self.remplissage, ordre_fabrication=of1)
        Affectation.objects.create(ouvrier=ouvrier, etape=self.remplissage, ordre_fabrication=of2)
        self.assertEqual(a1.date_debut, AUJOURDHUI)                                  # reprise de l'OF

    def test_poste_determine_l_etape_et_of_verrouille_refuse(self):
        ouvrier = self.ouvrier()
        affectation = self.affecter(ouvrier, etape=None, poste=self.poste)
        self.assertEqual(affectation.etape, self.remplissage)
        with self.assertRaisesMessage(ValidationError, "correspond à l'étape"):
            self.affecter(self.ouvrier(competences=[self.remplissage, self.nettoyage]), etape=self.nettoyage, poste=self.poste)
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        of.annuler("Test")
        with self.assertRaisesMessage(ValidationError, "annulé"):
            Affectation.objects.create(ouvrier=ouvrier, etape=self.remplissage, ordre_fabrication=of)

    def test_affectation_api_enregistre_l_auteur(self):
        ouvrier = self.ouvrier()
        r = self.api.post("/api/personnel/affectations/", {"ouvrier": ouvrier.id, "poste": self.poste.id, "date_debut": str(AUJOURDHUI)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data["affecte_par"], r.data["etape_libelle"], r.data["poste_code"]), (self.admin.id, self.remplissage.libelle, self.poste.code))
        r = self.api.get(f"/api/personnel/affectations/?active_le={AUJOURDHUI}")
        self.assertEqual(r.data["count"], 1)

    # -- départ, contrat, compétences -----------------------------------------
    def test_depart_motif_obligatoire_clot_les_affectations(self):
        ouvrier = self.ouvrier()
        en_cours = self.affecter(ouvrier, date_debut=AUJOURDHUI - timedelta(days=3), date_fin=AUJOURDHUI + timedelta(days=3))
        self.affecter(ouvrier, date_debut=AUJOURDHUI + timedelta(days=10))
        ouvrier.actif = False
        with self.assertRaisesMessage(ValidationError, "motif de sortie"):
            ouvrier.save()
        ouvrier.motif_sortie = "Fin de collaboration"
        ouvrier.save()
        en_cours.refresh_from_db()
        self.assertEqual((en_cours.date_fin, Affectation.objects.count()), (AUJOURDHUI, 1))
        with self.assertRaisesMessage(ValidationError, "plus actif"):
            self.affecter(ouvrier)
        with self.assertRaisesMessage(ValidationError, "désactivez-le"):
            ouvrier.delete()

    def test_contrat_raccourci_ou_competence_retiree_avec_affectation_en_cours_refuse(self):
        ouvrier = self.ouvrier("TEMPORAIRE", fin=AUJOURDHUI + timedelta(days=30))
        self.affecter(ouvrier, date_fin=AUJOURDHUI + timedelta(days=20))
        ouvrier.date_fin_contrat = AUJOURDHUI + timedelta(days=10)
        with self.assertRaisesMessage(ValidationError, "sortent de la période de contrat"):
            ouvrier.save()
        r = self.assert_refus(self.api.patch(f"/api/personnel/ouvriers/{ouvrier.id}/", {"competences": [self.nettoyage.id]}, format="json"))
        self.assertIn("competences", r.data)

    def test_ouvriers_disponibles(self):
        libre = self.ouvrier()
        occupe = self.ouvrier()
        self.ouvrier(competences=[self.nettoyage])                                    # pas compétent
        self.ouvrier("TEMPORAIRE", fin=AUJOURDHUI - timedelta(days=1), entree=AUJOURDHUI - timedelta(days=20))  # contrat fini
        self.affecter(occupe)
        r = self.api.get(f"/api/personnel/ouvriers/disponibles/?etape={self.remplissage.id}")
        self.assertEqual([o["id"] for o in r.data], [libre.id])
        self.assert_refus(self.api.get("/api/personnel/ouvriers/disponibles/"))

    # -- droits ---------------------------------------------------------------
    def test_droits_par_profil(self):
        def client(profil):
            api = APIClient()
            api.force_authenticate(Utilisateur.objects.create_user(profil.lower(), password="x", profil=profil))
            return api
        donnees = {"nom": "A", "prenom": "B", "type_contrat": "PERMANENT", "date_entree": str(AUJOURDHUI)}
        self.assertEqual(client(Profil.RESPONSABLE_PRODUCTION).post("/api/personnel/ouvriers/", donnees, format="json").status_code, 201)
        agent = client(Profil.AGENT_PRODUCTION)
        self.assertEqual(agent.get("/api/personnel/ouvriers/").status_code, 200)
        self.assertEqual(agent.post("/api/personnel/ouvriers/", donnees, format="json").status_code, 403)
        self.assertEqual(client(Profil.MAGASINIER).get("/api/personnel/ouvriers/").status_code, 403)
        self.assertEqual(client(Profil.CAISSIER).get("/api/personnel/affectations/").status_code, 403)
