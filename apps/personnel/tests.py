from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from apps.comptes.models import Profil, Utilisateur
from apps.core.tests import BaseValidation
from apps.industriel.models import Activite, EtapeStandard, Ligne, Poste, Usine
from apps.production.models import OrdreFabrication
from apps.personnel.models import Affectation, ConditionRemuneration, Ouvrier, Pointage

AUJOURDHUI = timezone.localdate()


class BasePersonnel(BaseValidation):
    """Étapes, ligne, poste et utilitaires communs (aucun test ici)."""

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



class PersonnelTests(BasePersonnel):
    """Phase 1 : registre des ouvriers et affectations."""

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
        self.assertEqual(client(Profil.RH).post("/api/personnel/ouvriers/", donnees, format="json").status_code, 201)
        production = client(Profil.RESPONSABLE_PRODUCTION)                           # consulte, affecte
        self.assertEqual(production.get("/api/personnel/ouvriers/").status_code, 200)
        self.assertEqual(production.post("/api/personnel/ouvriers/", donnees, format="json").status_code, 403)
        ouvrier = self.ouvrier()
        r = production.post("/api/personnel/affectations/", {"ouvrier": ouvrier.id, "etape": self.remplissage.id, "date_debut": str(AUJOURDHUI)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(production.get("/api/personnel/remunerations/").status_code, 403)  # jamais les montants
        self.assertEqual(production.get("/api/personnel/pointages/").status_code, 200)
        self.assertEqual(production.post("/api/personnel/pointages/", {"ouvrier": ouvrier.id, "date": str(AUJOURDHUI)}, format="json").status_code, 403)
        daf = client(Profil.COMPTABILITE_DAF)
        self.assertEqual(daf.get("/api/personnel/remunerations/").status_code, 200)
        self.assertEqual(daf.post("/api/personnel/remunerations/", {}, format="json").status_code, 403)
        agent = client(Profil.AGENT_PRODUCTION)
        self.assertEqual(agent.get("/api/personnel/ouvriers/").status_code, 200)
        self.assertEqual(agent.post("/api/personnel/ouvriers/", donnees, format="json").status_code, 403)
        self.assertEqual(client(Profil.MAGASINIER).get("/api/personnel/ouvriers/").status_code, 403)
        self.assertEqual(client(Profil.CAISSIER).get("/api/personnel/affectations/").status_code, 403)


class RemunerationEtPointageTests(BasePersonnel):
    """Phase 2 : conditions de rémunération historisées, pointages journaliers."""

    def test_condition_historisee_et_figee_une_fois_appliquee(self):
        ouvrier = self.ouvrier()
        debut = ouvrier.date_entree
        ancienne = ConditionRemuneration.objects.create(ouvrier=ouvrier, mode="MENSUEL", montant=90000, date_effet=debut)
        nouvelle = ConditionRemuneration.objects.create(ouvrier=ouvrier, mode="MENSUEL", montant=100000, date_effet=AUJOURDHUI)
        self.assertEqual(ouvrier.condition_au(AUJOURDHUI - timedelta(days=1)), ancienne)
        self.assertEqual(ouvrier.condition_au(AUJOURDHUI), nouvelle)
        pointage = Pointage.objects.create(ouvrier=ouvrier, date=debut + timedelta(days=1))
        pointage.valider(self.admin)
        ancienne.montant = 95000
        with self.assertRaisesMessage(ValidationError, "créez une nouvelle condition"):
            ancienne.save()
        with self.assertRaisesMessage(ValidationError, "pointages validés"):
            ancienne.delete()
        nouvelle.montant = 110000                                                    # aucun pointage validé couvert
        nouvelle.save()
        with self.assertRaisesMessage(ValidationError, "strictement positif"):
            ConditionRemuneration.objects.create(ouvrier=ouvrier, mode="JOURNALIER", montant=0, date_effet=AUJOURDHUI - timedelta(days=2))

    def test_pointage_reprend_l_affectation_du_jour(self):
        ouvrier = self.ouvrier()
        self.affecter(ouvrier, poste=self.poste, etape=None, date_debut=AUJOURDHUI - timedelta(days=5))
        pointage = Pointage.objects.create(ouvrier=ouvrier, date=AUJOURDHUI)
        self.assertEqual((pointage.poste, pointage.etape, pointage.ordre_fabrication), (self.poste, self.remplissage, None))
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin, date_prevue=AUJOURDHUI - timedelta(days=1))
        Affectation.objects.create(ouvrier=ouvrier, etape=self.remplissage, ordre_fabrication=of)
        hier = Pointage.objects.create(ouvrier=ouvrier, date=AUJOURDHUI - timedelta(days=1))  # l'OF du jour prime
        self.assertEqual(hier.ordre_fabrication, of)
        absent = Pointage.objects.create(ouvrier=ouvrier, date=AUJOURDHUI - timedelta(days=2), presence="ABSENT")
        self.assertEqual((absent.etape, absent.fraction_jour), (None, 0))

    def test_regles_du_pointage(self):
        ouvrier = self.ouvrier()
        with self.assertRaisesMessage(ValidationError, "jour à venir"):
            Pointage.objects.create(ouvrier=ouvrier, date=AUJOURDHUI + timedelta(days=1))
        with self.assertRaisesMessage(ValidationError, "pas sous contrat"):
            Pointage.objects.create(ouvrier=ouvrier, date=ouvrier.date_entree - timedelta(days=1))
        with self.assertRaisesMessage(ValidationError, "motif de l'absence"):
            Pointage.objects.create(ouvrier=ouvrier, date=AUJOURDHUI, presence="ABSENT", absence_justifiee=True)
        of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin)
        with self.assertRaisesMessage(ValidationError, "n'est pas affecté à l'OF"):
            Pointage.objects.create(ouvrier=ouvrier, date=AUJOURDHUI, ordre_fabrication=of)
        pointage = Pointage.objects.create(ouvrier=ouvrier, date=AUJOURDHUI, presence="DEMI_JOURNEE")
        self.assertEqual(pointage.fraction_jour, Decimal("0.5"))
        pointage.valider(self.admin)
        pointage.presence = "PRESENT"
        with self.assertRaisesMessage(ValidationError, "validé"):
            pointage.save()
        with self.assertRaisesMessage(ValidationError, "validé"):
            pointage.delete()
        with self.assertRaises(ValueError):
            pointage.valider(self.admin)

    def test_feuille_saisie_du_jour_et_validation_de_periode(self):
        a, b = self.ouvrier(), self.ouvrier()
        self.affecter(a, poste=self.poste, etape=None)
        feuille = self.api.get(f"/api/personnel/pointages/feuille/?date={AUJOURDHUI}").data
        self.assertEqual({l["ouvrier"] for l in feuille["lignes"]}, {a.id, b.id})
        ligne_a = next(l for l in feuille["lignes"] if l["ouvrier"] == a.id)
        self.assertEqual((ligne_a["affectations"][0]["poste_code"], ligne_a["pointage"]), (self.poste.code, None))
        # Une ligne refusée : rien n'est enregistré.
        r = self.api.post("/api/personnel/pointages/saisie_jour/", {"date": str(AUJOURDHUI), "lignes": [
            {"ouvrier": a.id, "presence": "PRESENT"},
            {"ouvrier": b.id, "presence": "ABSENT", "absence_justifiee": True},
        ]}, format="json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertIn(str(b.id), r.data["erreurs"])
        self.assertFalse(Pointage.objects.exists())
        r = self.api.post("/api/personnel/pointages/saisie_jour/", {"date": str(AUJOURDHUI), "lignes": [
            {"ouvrier": a.id, "presence": "PRESENT"},
            {"ouvrier": b.id, "presence": "ABSENT", "absence_justifiee": True, "motif_absence": "Maladie"},
        ]}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Pointage.objects.get(ouvrier=a).poste, self.poste)
        r = self.api.post("/api/personnel/pointages/saisie_jour/", {"date": str(AUJOURDHUI), "lignes": [
            {"ouvrier": b.id, "presence": "PRESENT"}]}, format="json")            # correction avant validation
        self.assertEqual((r.status_code, Pointage.objects.get(ouvrier=b).presence), (201, "PRESENT"))
        r = self.api.post("/api/personnel/pointages/valider_periode/", {"du": str(AUJOURDHUI), "au": str(AUJOURDHUI)}, format="json")
        self.assertEqual(r.data["valides"], 2)
        r = self.api.post("/api/personnel/pointages/saisie_jour/", {"date": str(AUJOURDHUI), "lignes": [
            {"ouvrier": b.id, "presence": "ABSENT"}]}, format="json")             # validé : refusé
        self.assertEqual(r.status_code, 400, r.content)
        historique = self.api.get(f"/api/personnel/pointages/{Pointage.objects.get(ouvrier=a).id}/").data
        self.assertEqual((historique["statut"], historique["valide_par"]), ("VALIDE", self.admin.id))



class PaieTests(BasePersonnel):
    """Phase 3 : états de paie, validation DAF, paiement en espèces, coûts des OF."""
    OCTOBRE = date(2026, 10, 15)     # octobre 2026 : 22 jours ouvrables (lundi-vendredi)

    def setUp(self):
        super().setUp()
        from apps.caisse.models import Caisse, SessionCaisse
        def utilisateur(profil):
            u = Utilisateur.objects.create_user(profil.lower(), password="x", profil=profil)
            api = APIClient()
            api.force_authenticate(u)
            return u, api
        self.rh, self.api_rh = utilisateur(Profil.RH)
        self.daf, self.api_daf = utilisateur(Profil.COMPTABILITE_DAF)
        self.caissier, self.api_caisse = utilisateur(Profil.CAISSIER)
        from apps.caisse.models import Encaissement
        from apps.commercial.models import Facture
        caisse = Caisse.objects.create(nom="Caisse paie", caissier=self.caissier)
        session = SessionCaisse.objects.create(caisse=caisse, caissier=self.caissier, solde_ouverture=0)
        # Argent en caisse : une vente encaissée en espèces (le solde d'ouverture est automatique).
        self.client_evam.encours_autorise = 1000000
        self.client_evam.save()
        facture = Facture.objects.create(commande=self.commande(lignes=((2500, 100),), statut="VALIDEE"))
        facture.generer_lignes_depuis_commande()
        Encaissement.objects.create(session_caisse=session, facture=facture, montant=250000, mode_paiement="ESPECES")
        self.permanent = self.ouvrier(entree=date(2026, 9, 1))
        ConditionRemuneration.objects.create(ouvrier=self.permanent, mode="MENSUEL", montant=220000, date_effet=date(2026, 9, 1))
        self.of = OrdreFabrication.objects.create(article=self.produit, quantite_a_produire=1, responsable=self.admin, date_prevue=date(2026, 10, 8))
        Affectation.objects.create(ouvrier=self.permanent, etape=self.remplissage, ordre_fabrication=self.of, date_fin=date(2026, 10, 8))

    def pointer(self, ouvrier, jour, presence="PRESENT", valider=True, **champs):
        pointage = Pointage.objects.create(ouvrier=ouvrier, date=jour, presence=presence, **champs)
        if valider:
            pointage.valider(self.rh)
        return pointage

    def pointer_octobre(self):
        self.pointer(self.permanent, date(2026, 10, 5), "ABSENT")                                       # retenu : 1
        self.pointer(self.permanent, date(2026, 10, 6), "ABSENT", absence_justifiee=True, motif_absence="Maladie")
        self.pointer(self.permanent, date(2026, 10, 7), "DEMI_JOURNEE")                                 # retenu : 0,5
        self.pointer(self.permanent, date(2026, 10, 8), ordre_fabrication=self.of)                      # sur l'OF

    def preparer(self, periodicite="MENSUELLE", jour=None):
        r = self.api_rh.post("/api/personnel/etats-paie/preparer/", {"periodicite": periodicite, "date": str(jour or self.OCTOBRE)}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.data

    def test_salaire_mensuel_retenue_au_prorata(self):
        from apps.personnel.models import EtatPaie
        self.pointer_octobre()
        resultat = self.preparer()
        self.assertEqual(resultat["erreurs"], {})
        etat = EtatPaie.objects.get()
        # 220 000 / 22 = 10 000 par jour ouvrable ; 1,5 jour d'absence non justifiée retenu.
        self.assertEqual((etat.date_debut, etat.date_fin), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual((etat.montant, etat.jours_absence_retenus, etat.jours_non_pointes, etat.jours_travailles),
                         (Decimal("205000"), Decimal("1.5"), 18, Decimal("1.5")))
        self.assertEqual(self.preparer()["etats"], [])                               # pas de doublon

    def test_journalier_hebdomadaire_et_entree_en_cours_de_mois(self):
        from apps.personnel.models import EtatPaie
        temporaire = self.ouvrier("TEMPORAIRE", fin=date(2026, 12, 31), entree=date(2026, 10, 1))
        ConditionRemuneration.objects.create(ouvrier=temporaire, mode="JOURNALIER", montant=5000,
                                             periodicite_paie="HEBDOMADAIRE", date_effet=date(2026, 10, 1))
        self.pointer(temporaire, date(2026, 10, 12))
        self.pointer(temporaire, date(2026, 10, 13), "DEMI_JOURNEE")
        self.pointer(temporaire, date(2026, 10, 17))                                  # samedi travaillé : payé
        self.preparer("HEBDOMADAIRE", date(2026, 10, 14))
        etat = EtatPaie.objects.get(ouvrier=temporaire)
        self.assertEqual((etat.date_debut, etat.date_fin, etat.montant), (date(2026, 10, 12), date(2026, 10, 18), Decimal("12500")))
        self.assertFalse(EtatPaie.objects.filter(ouvrier=self.permanent).exists())  # payé au mois
        # Entrée le jeudi 15/10 : seuls les jours ouvrables sous contrat comptent (12 sur 22).
        nouveau = self.ouvrier(entree=date(2026, 10, 15))
        ConditionRemuneration.objects.create(ouvrier=nouveau, mode="MENSUEL", montant=220000, date_effet=date(2026, 10, 15))
        self.preparer()
        self.assertEqual(EtatPaie.objects.get(ouvrier=nouveau).montant, Decimal("120000"))

    def test_pointages_non_valides_bloquent_la_preparation(self):
        self.pointer(self.permanent, date(2026, 10, 5), valider=False)
        resultat = self.preparer()
        self.assertEqual(resultat["etats"], [])
        self.assertIn("non validé", resultat["erreurs"][self.permanent.matricule][0])

    def test_circuit_complet_rh_daf_caisse(self):
        from apps.caisse.models import Decaissement
        from apps.comptabilite.ecritures import ecritures_de
        from apps.couts.models import CoutMainOeuvre
        from apps.personnel.models import EtatPaie
        self.pointer_octobre()
        etat_id = self.preparer()["etats"][0]["id"]
        url = f"/api/personnel/etats-paie/{etat_id}"
        self.assertEqual(self.api_rh.post(f"{url}/valider/").status_code, 403)                   # le RH ne valide pas
        self.assertEqual(self.api_caisse.get(f"{url}/").status_code, 404)                        # pas encore à payer
        r = self.api_daf.post(f"{url}/valider/")
        self.assertEqual((r.status_code, r.data["statut"]), (200, "VALIDE"), r.content)
        etat = EtatPaie.objects.get()
        lignes = {(l.compte, l.compte_tiers, l.debit, l.credit) for e in ecritures_de(etat) for l in e.lignes.all()}
        self.assertEqual(lignes, {("661", "", Decimal("205000.00"), Decimal("0")),
                                  ("422", self.permanent.matricule, Decimal("0"), Decimal("205000.00"))})
        cout = CoutMainOeuvre.objects.get(etat_paie=etat)                                         # 1 jour sur l'OF
        self.assertEqual((cout.ordre_fabrication, cout.heures, cout.cout_horaire), (self.of, Decimal("8"), Decimal("1250")))
        # Période arrêtée : plus de pointage ni de nouveau taux sur octobre.
        with self.assertRaisesMessage(ValidationError, "déjà validé"):
            self.pointer(self.permanent, date(2026, 10, 9))
        with self.assertRaisesMessage(ValidationError, "déjà arrêtée"):
            ConditionRemuneration.objects.create(ouvrier=self.permanent, mode="MENSUEL", montant=250000, date_effet=date(2026, 10, 20))
        # Paiement en espèces.
        self.assertEqual(self.api_daf.post(f"{url}/payer/").status_code, 403)
        r = self.api_caisse.post(f"{url}/payer/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["statut"], "PAYE")
        decaissement = Decaissement.objects.get()
        self.assertEqual((decaissement.statut, decaissement.montant, decaissement.autorise_par), ("EFFECTUE", Decimal("205000"), self.daf))
        lignes = {(l.compte, l.compte_tiers, l.debit, l.credit) for e in ecritures_de(decaissement) for l in e.lignes.all()}
        self.assertEqual(lignes, {("422", self.permanent.matricule, Decimal("205000.00"), Decimal("0")),
                                  ("571", "", Decimal("0"), Decimal("205000.00"))})
        self.assertEqual(self.api_caisse.post(f"{url}/payer/").status_code, 400)                # pas deux fois
        r = self.api_rh.get("/api/personnel/etats-paie/emargement/?date_debut=2026-10-01&date_fin=2026-10-31")
        self.assertEqual((r.status_code, r["Content-Type"]), (200, "application/pdf"))

    def test_annulation_et_pointages_modifies_depuis_la_preparation(self):
        from apps.comptabilite.ecritures import ecritures_de
        from apps.couts.models import CoutMainOeuvre
        from apps.personnel.models import EtatPaie
        self.pointer_octobre()
        etat_id = self.preparer()["etats"][0]["id"]
        url = f"/api/personnel/etats-paie/{etat_id}"
        self.pointer(self.permanent, date(2026, 10, 9), "ABSENT")                                # après préparation
        r = self.api_daf.post(f"{url}/valider/")
        self.assertEqual(r.status_code, 400)
        self.assertIn("recalculer", r.data["erreur"])
        self.assertEqual(self.api_rh.post(f"{url}/recalculer/").data["montant"], "195000.00")
        self.assertEqual(self.api_daf.post(f"{url}/valider/").status_code, 200)
        self.assertEqual(self.api_daf.post(f"{url}/annuler/", {}, format="json").status_code, 400)   # motif obligatoire
        r = self.api_daf.post(f"{url}/annuler/", {"motif": "Erreur de taux"}, format="json")
        self.assertEqual((r.status_code, r.data["statut"]), (200, "ANNULE"), r.content)
        etat = EtatPaie.objects.get()
        soldes = {}
        for ligne in (l for e in ecritures_de(etat) for l in e.lignes.all()):
            soldes[ligne.compte] = soldes.get(ligne.compte, 0) + ligne.debit - ligne.credit
        self.assertEqual(soldes, {"661": 0, "422": 0})                                           # contre-passé
        self.assertFalse(CoutMainOeuvre.objects.exists())
        self.assertEqual(len(self.preparer()["etats"]), 1)                                       # nouvelle paie possible
        self.assertEqual(self.api_rh.delete(f"/api/personnel/etats-paie/{EtatPaie.objects.get(statut='BROUILLON').id}/").status_code, 204)
