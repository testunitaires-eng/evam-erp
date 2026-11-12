from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.comptes.models import Profil, Utilisateur
from apps.eau.calculs import CalculImpossible, calcul_previsionnel, proposer_standard
from apps.eau.traitement import synthese_mois
from apps.eau.models import (
    Bloc, CaracteristiquesEquipement, Compteur, CoutStandardEau, ElementCout, ExceptionHeures, ParametresEau, PerteEau,
    Periode, PrevisionCaptage, PrevisionVolume, ReleveCompteur, VersionElementCout, bloc_de_l_equipement, coefficient_mensuel, montant_mensuel_etale,
    montant_mensuel_frequence, mois_courant, mois_suivant,
)
from apps.industriel.models import Activite, Equipement, EtapeStandard, Ligne, Poste, Usine
from apps.referentiel.models import Article, FamilleArticle, FormatArticle, UniteVenteArticle

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


# =====================================================================
# Phase 2 - le calcul du classeur (onglet « Calcul coût eau »)
# =====================================================================

# étape, libellé, famille, catégorie, unité, quantité, prix, fréquence, période, durée, coût mensuel attendu
CHARGES_DU_CLASSEUR = [
    ("CAPTAGE", "Électricité pompe du forage", "COURANTE", "ELECTRICITE", "kW", 5, 100, 720, "MOIS", None, "144000.00"),
    ("CAPTAGE", "Carburant groupe électrogène (à confirmer)", "COURANTE", "CARBURANT", "L", None, None, None, None, None, "0.00"),
    ("CAPTAGE", "Amortissement installation du forage", "ETALEE", "AMORTISSEMENT", "lot", 1, 12000000, None, None, 120, "40000.00"),
    ("CAPTAGE", "Entretien préventif pompe du forage", "PREVENTIVE", "MAINTENANCE_PREVENTIVE", "entretien", 1, 120000, 3, "AN", None, "12000.00"),
    ("PREFILTRATION", "Électricité pompe d'alimentation des filtres", "COURANTE", "ELECTRICITE", "kW", 2, 100, 200, "MOIS", None, "40000.00"),
    ("PREFILTRATION", "Sable du filtre à sable", "ETALEE", "DUREE_DE_VIE", "kg", 500, 400, None, None, 24, "8333.33"),
    ("PREFILTRATION", "Charbon actif", "ETALEE", "DUREE_DE_VIE", "kg", 200, 3000, None, None, 12, "50000.00"),
    ("PREFILTRATION", "Résine de l'adoucisseur", "ETALEE", "DUREE_DE_VIE", "L", 100, 5000, None, None, 60, "8333.33"),
    ("PREFILTRATION", "Sel de régénération", "COURANTE", "CONSOMMABLE", "kg", 50, 300, 4, "MOIS", None, "60000.00"),
    ("PREFILTRATION", "Produit de lavage des filtres", "PREVENTIVE", "MAINTENANCE_PREVENTIVE", "L", 5, 2000, 2, "MOIS", None, "20000.00"),
    ("PREFILTRATION", "Amortissement des corps de filtres", "ETALEE", "AMORTISSEMENT", "unité", 3, 1500000, None, None, 120, "37500.00"),
    ("ULTRAFILTRATION", "Électricité pompe de l'ultrafiltration", "COURANTE", "ELECTRICITE", "kW", 3, 100, 200, "MOIS", None, "60000.00"),
    ("ULTRAFILTRATION", "Membrane DP1 (0,01 µ)", "ETALEE", "DUREE_DE_VIE", "unité", 1, 1000000, None, None, 48, "20833.33"),
    ("ULTRAFILTRATION", "Membrane DP2 (0,02 µ)", "ETALEE", "DUREE_DE_VIE", "unité", 1, 1000000, None, None, 48, "20833.33"),
    ("ULTRAFILTRATION", "Membrane DP3 (0,1 µ)", "ETALEE", "DUREE_DE_VIE", "unité", 1, 1000000, None, None, 48, "20833.33"),
    ("ULTRAFILTRATION", "Amortissement module d'ultrafiltration", "ETALEE", "AMORTISSEMENT", "lot", 1, 6000000, None, None, 120, "50000.00"),
    ("CUVES_EAU", "Nettoyage de la cuve eau traitée", "PREVENTIVE", "MAINTENANCE_PREVENTIVE", "L", 10, 3000, 4, "AN", None, "10000.00"),
    ("CUVES_EAU", "Amortissement cuves eau brute et eau traitée", "ETALEE", "AMORTISSEMENT", "unité", 2, 2400000, None, None, 120, "40000.00"),
    ("UV", "Électricité lampe(s) UV", "COURANTE", "ELECTRICITE", "kW", Decimal("0.1"), 100, 200, "MOIS", None, "2000.00"),
    ("UV", "Lampe(s) UV", "ETALEE", "DUREE_DE_VIE", "unité", 2, 120000, None, None, 12, "20000.00"),
    ("UV", "Gaine quartz", "ETALEE", "DUREE_DE_VIE", "unité", 2, 60000, None, None, 24, "5000.00"),
    ("UV", "Amortissement réacteur UV", "ETALEE", "AMORTISSEMENT", "unité", 1, 1200000, None, None, 120, "10000.00"),
    ("CONTROLE_QUALITE_EAU", "Analyses par laboratoire externe", "COURANTE", "ANALYSE", "analyse", 1, 50000, 2, "MOIS", None, "100000.00"),
    ("CONTROLE_QUALITE_EAU", "Kits de contrôle interne", "COURANTE", "ANALYSE", "kit", 1, 10000, 1, "SEMAINE", None, "43333.33"),
    # Une charge au besoin existe pour le réel mais n'entre jamais dans le prévisionnel.
    ("ULTRAFILTRATION", "Réparation pompe de l'ultrafiltration", "AU_BESOIN", "MAINTENANCE_AU_BESOIN", "", None, None, None, None, None, "0.00"),
]


class BaseClasseur(BaseEau):
    """Toutes les données de test de l'onglet « Calcul coût eau », applicables depuis le mois dernier."""

    def setUp(self):
        super().setUp()
        self.formats = {}
        for nom, contenance, bouteilles in (("150 cl", "1.5", 100000), ("50 cl", "0.5", 60000), ("500 cl", "5", 4000)):
            article = Article.objects.create(
                type_article="PRODUIT_FINI", unite_mesure="UNITE", famille=FamilleArticle.objects.get_or_create(nom="Eau")[0],
                format=FormatArticle.objects.get_or_create(valeur=nom)[0],
                unite_vente=UniteVenteArticle.objects.get_or_create(nom="Pack de 6")[0],
                contenance=Decimal(contenance), unite_contenance="L",
            )
            self.formats[nom] = article
            PrevisionVolume.objects.create(usine=self.usine, article=article, mois_application=self.passe, bouteilles_par_mois=bouteilles)
        PrevisionCaptage.objects.create(usine=self.usine, mois_application=self.passe, volume_site_eau_m3=220, volume_autres_sites_m3=330)
        self.elements = {}
        for ordre, (etape, libelle, famille, categorie, unite, quantite, prix, frequence, periode, duree, _) in enumerate(CHARGES_DU_CLASSEUR):
            element = ElementCout.objects.create(
                usine=self.usine, libelle=libelle, etape=EtapeStandard.objects.get(code=etape), famille=famille,
                categorie=categorie, unite=unite, ordre=ordre,
            )
            self.elements[libelle] = element
            if quantite is not None:
                VersionElementCout.objects.create(
                    element=element, mois_application=self.passe, quantite=quantite, prix_unitaire=prix,
                    frequence=frequence, periode=periode or "", duree_vie_mois=duree,
                )


class CalculClasseurTests(BaseClasseur):

    def test_le_calcul_retrouve_exactement_le_classeur(self):
        calcul = calcul_previsionnel(self.usine, self.courant)
        self.assertEqual(calcul["volume"]["total_m3"], "200")
        self.assertEqual(calcul["partage_forage"]["part_site_eau"], "0.4")
        attendus = {ligne[1]: ligne[-1] for ligne in CHARGES_DU_CLASSEUR}
        self.assertEqual({ligne["libelle"]: ligne["cout_mensuel"] for ligne in calcul["charges"]}, attendus)
        self.assertEqual(calcul["synthese"], {
            "cout_forage": "196000.00", "cout_forage_m3": "980.00",
            "cout_traitement": "627000.00", "cout_traitement_m3": "3135.00",
            "cout_mensuel": "823000.00", "cout_m3": "4115.00", "cout_litre": "4.115", "controle": "OK",
        })
        self.assertEqual(calcul["bloquants"], [])
        self.assertEqual(calcul["alertes"], ["« Carburant groupe électrogène (à confirmer) » n'est pas chiffré pour ce mois : compté 0."])
        ligne = next(l for l in calcul["charges"] if l["libelle"] == "Électricité pompe du forage")
        self.assertEqual((ligne["bloc"], ligne["part_site"], ligne["cout_m3"]), ("FORAGE", "0.4", "720.00"))

    def test_une_modification_ne_change_que_les_mois_suivants(self):
        kits = self.elements["Kits de contrôle interne"]
        VersionElementCout.objects.create(element=kits, mois_application=self.suivant, quantite=1, prix_unitaire=12000, frequence=1, periode="SEMAINE")
        gaine = self.elements["Gaine quartz"]
        VersionElementCout.objects.create(element=gaine, mois_application=self.suivant, retire=True)
        self.assertEqual(calcul_previsionnel(self.usine, self.courant)["synthese"]["cout_mensuel"], "823000.00")
        suivant = calcul_previsionnel(self.usine, self.suivant)
        # kits : 12 000 x 52 / 12 = 52 000 (au lieu de 43 333,33) ; gaine retirée (- 5 000).
        self.assertEqual(suivant["synthese"]["cout_mensuel"], "826666.67")
        self.assertNotIn("Gaine quartz", [l["libelle"] for l in suivant["charges"]])
        # Le partage du forage change aussi au mois suivant seulement.
        PrevisionCaptage.objects.create(usine=self.usine, mois_application=self.suivant, volume_site_eau_m3=250, volume_autres_sites_m3=250)
        self.assertEqual(calcul_previsionnel(self.usine, self.courant)["synthese"]["cout_forage"], "196000.00")
        self.assertEqual(calcul_previsionnel(self.usine, self.suivant)["synthese"]["cout_forage"], "245000.00")

    def test_calcul_impossible_sans_volume_ou_sans_partage_du_forage(self):
        autre = Usine.objects.create(nom="Site sans prévision")
        self.assertTrue(calcul_previsionnel(autre, self.courant)["bloquants"])
        PrevisionCaptage.objects.all().delete()
        calcul = calcul_previsionnel(self.usine, self.courant)
        self.assertEqual(len(calcul["bloquants"]), 1)
        with self.assertRaises(CalculImpossible):
            proposer_standard(self.usine, self.courant)

    def test_valeurs_attendues_selon_la_famille(self):
        cas = [
            ("Charbon actif", {"quantite": 200, "prix_unitaire": 3000}),                                       # étalée sans durée
            ("Charbon actif", {"quantite": 200, "prix_unitaire": 3000, "duree_vie_mois": 12, "periode": "MOIS"}),
            ("Sel de régénération", {"quantite": 50, "prix_unitaire": 300, "frequence": 4}),                    # sans période
            ("Sel de régénération", {"quantite": 50, "prix_unitaire": 300, "frequence": 4, "periode": "MOIS", "duree_vie_mois": 3}),
            ("Réparation pompe de l'ultrafiltration", {"quantite": 1, "prix_unitaire": 300000}),                 # au besoin : jamais prévu
        ]
        for libelle, champs in cas:
            with self.assertRaises(ValidationError, msg=libelle):
                VersionElementCout.objects.create(element=self.elements[libelle], mois_application=self.suivant, **champs)

    def test_element_hors_coût_de_l_eau_et_famille_figee(self):
        with self.assertRaises(ValidationError):
            ElementCout.objects.create(usine=self.usine, libelle="Électricité soutireuse", etape=self.poste_remplissage.etape,
                                       famille="COURANTE", categorie="ELECTRICITE")
        with self.assertRaises(ValidationError):   # pompe du forage rattachée à une étape du traitement
            ElementCout.objects.create(usine=self.usine, libelle="X", etape=EtapeStandard.objects.get(code="UV"),
                                       equipement=self.pompe_forage, famille="COURANTE", categorie="ELECTRICITE")
        sel = self.elements["Sel de régénération"]
        sel.famille = "ETALEE"
        with self.assertRaises(ValidationError):
            sel.save()

    def test_prevision_de_volume_sur_un_vrai_format(self):
        matiere = Article.objects.create(code="SEL", type_article="MATIERE_PREMIERE", unite_mesure="KG")
        with self.assertRaises(ValidationError):
            PrevisionVolume.objects.create(usine=self.usine, article=matiere, mois_application=self.passe, bouteilles_par_mois=10)


class CoutStandardTests(BaseClasseur):
    """Le logiciel propose, le contrôle de gestion valide ; chaque version est historisée."""

    def test_proposer_valider_et_standard_en_vigueur(self):
        controle = self.client_pour(Profil.CONTROLE_GESTION)
        reponse = controle.post("/api/eau/couts-standards/proposer/", {"usine": self.usine.pk, "mois_application": self.passe}, format="json")
        self.assertEqual(reponse.status_code, 201, reponse.content)
        self.assertEqual((reponse.data["cout_m3"], reponse.data["statut"], reponse.data["cout_litre"]), ("4115.0000", "PROPOSE", "4.1150000"))
        self.assertEqual(reponse.data["detail"]["synthese"]["cout_mensuel"], "823000.00")
        premier = reponse.data["id"]
        # Rien ne s'applique tant que ce n'est pas validé.
        self.assertIsNone(controle.get(f"/api/eau/couts-standards/en_vigueur/?usine={self.usine.pk}").data)
        self.assertEqual(controle.post(f"/api/eau/couts-standards/{premier}/valider/").status_code, 200)
        en_vigueur = controle.get(f"/api/eau/couts-standards/en_vigueur/?usine={self.usine.pk}&mois={self.courant}").data
        self.assertEqual((en_vigueur["id"], en_vigueur["valide_par_nom"]), (premier, "controle_gestion"))
        historique = controle.get(f"/api/eau/couts-standards/{premier}/historique/").data
        self.assertEqual(len(historique), 2)
        # Un standard validé ne bouge plus.
        standard = CoutStandardEau.objects.get(pk=premier)
        with self.assertRaises(ValidationError):
            standard.delete()
        # Le suivant s'applique au plus tôt le mois prochain (règle 14).
        refuse = controle.post("/api/eau/couts-standards/proposer/", {"usine": self.usine.pk, "mois_application": self.courant}, format="json").data
        self.assertEqual(controle.post(f"/api/eau/couts-standards/{refuse['id']}/valider/").status_code, 400)
        self.assertEqual(controle.post(f"/api/eau/couts-standards/{refuse['id']}/rejeter/").status_code, 400)   # motif obligatoire
        self.assertEqual(controle.post(f"/api/eau/couts-standards/{refuse['id']}/rejeter/", {"motif": "Mois en cours"}, format="json").status_code, 200)
        suivant = controle.post("/api/eau/couts-standards/proposer/", {"usine": self.usine.pk, "mois_application": self.suivant}, format="json").data
        self.assertEqual(controle.post(f"/api/eau/couts-standards/{suivant['id']}/valider/").status_code, 200)
        self.assertEqual(controle.get(f"/api/eau/couts-standards/en_vigueur/?usine={self.usine.pk}&mois={self.courant}").data["id"], premier)
        self.assertEqual(controle.get(f"/api/eau/couts-standards/en_vigueur/?usine={self.usine.pk}&mois={self.suivant}").data["id"], suivant["id"])

    def test_droits_sur_le_calcul(self):
        url = f"/api/eau/couts-standards/calcul/?usine={self.usine.pk}&mois={self.courant}"
        self.assertEqual(self.client_pour(Profil.TECHNICIEN_EAU).get(url).status_code, 403)
        lecture = self.client_pour(Profil.COMPTABILITE_DAF)
        self.assertEqual(lecture.get(url).data["synthese"]["cout_m3"], "4115.00")
        self.assertEqual(lecture.post("/api/eau/couts-standards/proposer/", {"usine": self.usine.pk, "mois_application": self.passe}, format="json").status_code, 403)
        production = self.client_pour(Profil.RESPONSABLE_PRODUCTION)
        reponse = production.post("/api/eau/previsions-volumes/", {
            "usine": self.usine.pk, "article": self.formats["50 cl"].pk, "mois_application": self.suivant, "bouteilles_par_mois": 70000,
        }, format="json")
        self.assertEqual(reponse.status_code, 201, reponse.content)
        self.assertEqual(reponse.data["volume_m3"], "35.000")


# =====================================================================
# Phase 3 - saisies du traitement de l'eau
# =====================================================================

NOVEMBRE = "2025-11"   # 30 jours, 5 dimanches : 25 jours du lundi au samedi


def jour(numero, mois=11, annee=2025):
    return date(annee, mois, numero)


class BaseTraitement(BaseEau):
    def setUp(self):
        super().setUp()
        self.site_jus = Usine.objects.create(nom="Site jus test")
        self.compteur_forage = Compteur.objects.create(code="CF", libelle="Compteur du forage", type_compteur="COMPTEUR_FORAGE", usine=self.usine)
        self.debit_eau = Compteur.objects.create(code="D1", libelle="Forage -> site eau", type_compteur="DEBITMETRE", usine=self.usine, site_desservi=self.usine)
        self.debit_jus = Compteur.objects.create(code="D2", libelle="Forage -> site jus", type_compteur="DEBITMETRE", usine=self.usine, site_desservi=self.site_jus)
        # Le forage n'est pas sur la ligne de traitement (sa propre ligne).
        ligne_forage = Ligne.objects.create(designation="Forage", usine=self.usine, activite=self.poste_uf.ligne.activite)
        self.pompe_forage.poste = Poste.objects.create(ligne=ligne_forage, etape=self.poste_captage.etape)
        self.pompe_forage.save()
        self.ligne_traitement = self.poste_uf.ligne
        self.technicien = self.client_pour(Profil.TECHNICIEN_EAU)

    def relever(self, compteur, le, index):
        return ReleveCompteur.objects.create(compteur=compteur, date=le, index=index)

    def caracteristiques(self, equipement, **champs):
        return CaracteristiquesEquipement.objects.create(equipement=equipement, mois_application=NOVEMBRE, **champs)


class TraitementTests(BaseTraitement):

    def test_volumes_du_mois_et_part_du_site_eau(self):
        for compteur, octobre, mi_mois, fin in ((self.compteur_forage, 1000, 1300, 1560), (self.debit_eau, 400, 500, 620), (self.debit_jus, 600, 800, 930)):
            self.relever(compteur, jour(31, 10), octobre)
            self.relever(compteur, jour(15), mi_mois)
            self.relever(compteur, jour(30), fin)
        partage = synthese_mois(self.usine, NOVEMBRE)["partage_forage"]
        self.assertEqual(partage, {
            "volume_site_eau_m3": "220", "volume_autres_sites_m3": "330", "part_site_eau": "0.4",
            "compteur_forage_m3": "560", "ecart_compteur_debitmetres_m3": "10",
        })

    def test_un_debitmetre_non_releve_bloque_la_part(self):
        self.relever(self.debit_eau, jour(30), 100)
        synthese = synthese_mois(self.usine, NOVEMBRE)
        self.assertIsNone(synthese["partage_forage"]["part_site_eau"])
        self.assertTrue(any("D2" in alerte for alerte in synthese["alertes"]))

    def test_index_jamais_en_baisse_ni_dans_le_futur(self):
        self.relever(self.debit_eau, jour(10), 500)
        self.relever(self.debit_eau, jour(20), 600)
        for le, index in ((jour(15), 450), (jour(15), 650), (jour(25), 590), (jour(10), 520)):
            with self.assertRaises(ValidationError):
                self.relever(self.debit_eau, le, index)
        with self.assertRaises(ValidationError):
            self.relever(self.debit_eau, timezone.localdate() + timedelta(days=1), 900)

    def test_heures_standard_moins_les_exceptions(self):
        self.caracteristiques(self.pompe_forage, puissance_kw=5, heures_marche_jour=24)
        self.caracteristiques(self.pompe_uf, puissance_kw=3, heures_marche_jour=8, jours_de_marche="LUNDI_SAMEDI")
        self.caracteristiques(self.soutireuse, puissance_kw=10, heures_marche_jour=8, jours_de_marche="LUNDI_SAMEDI")
        heures = lambda: {l["designation"]: (l["heures_retenues"], l["kw_heures"], l["bloc"]) for l in synthese_mois(self.usine, NOVEMBRE)["heures_machine"]}
        self.assertEqual(heures(), {
            "Pompe du forage": ("720", "3600", "FORAGE"), "Pompe UF": ("200", "600", "TRAITEMENT"), "Soutireuse": ("200", "2000", None),
        })
        # Scénario, mois 2 : la ligne de traitement s'arrête 20 h (8 + 8 + 4).
        for numero, heures_arret in ((3, 8), (4, 8), (5, 4)):
            ExceptionHeures.objects.create(date=jour(numero), ligne=self.ligne_traitement, heures_en_moins=heures_arret, motif="PANNE")
        ExceptionHeures.objects.create(date=jour(2), ligne=self.ligne_traitement, heures_en_moins=5, motif="PANNE")    # dimanche : ne tourne pas
        ExceptionHeures.objects.create(date=jour(6), equipement=self.pompe_uf, heures_en_moins=12, motif="PANNE")    # plafonné aux 8 h du jour
        self.assertEqual(heures(), {
            "Pompe du forage": ("720", "3600", "FORAGE"), "Pompe UF": ("172", "516", "TRAITEMENT"), "Soutireuse": ("180", "1800", None),
        })
        self.assertEqual(synthese_mois(self.usine, NOVEMBRE)["total_kw_heures"], "5916")

    def test_exception_sur_un_equipement_ou_une_ligne(self):
        for champs in ({}, {"equipement": self.pompe_uf, "ligne": self.ligne_traitement}, {"equipement": self.pompe_uf, "heures_en_moins": 25},
                       {"equipement": self.pompe_uf, "motif": "AUTRE"}):
            donnees = {"date": jour(3), "heures_en_moins": 2, "motif": "PANNE", **champs}
            with self.assertRaises(ValidationError):
                ExceptionHeures.objects.create(**donnees)

    def test_alerte_pression_trop_haute(self):
        from apps.core.models import Notification
        membrane = Equipement.objects.create(designation="Membrane DP1", type_equipement="TRAITEMENT", usine=self.usine, poste=self.poste_uf)
        CaracteristiquesEquipement.objects.create(equipement=membrane, mois_application=self.passe, pression_max_bar=Decimal("2.5"))
        Utilisateur.objects.create_user("technicien2", password="x", profil=Profil.TECHNICIEN_EAU)
        reponse = self.technicien.post("/api/eau/releves-pression/", {"equipement": membrane.pk, "date": str(timezone.localdate()), "pression_bar": "2.4"}, format="json")
        self.assertEqual(reponse.status_code, 201, reponse.content)
        self.assertFalse(reponse.data["au_dessus_du_seuil"])
        self.assertFalse(Notification.objects.exists())
        reponse = self.technicien.post("/api/eau/releves-pression/", {"equipement": membrane.pk, "date": str(timezone.localdate()), "pression_bar": "3"}, format="json")
        self.assertTrue(reponse.data["au_dessus_du_seuil"])
        # L'auteur n'est pas notifié de sa propre saisie ; l'autre technicien l'est.
        self.assertEqual(list(Notification.objects.values_list("destinataire__username", flat=True)), ["technicien2"])

    def test_pertes_type_selon_la_cause_et_volume(self):
        format_15 = Article.objects.create(
            type_article="PRODUIT_FINI", unite_mesure="UNITE", famille=FamilleArticle.objects.get_or_create(nom="Eau")[0],
            format=FormatArticle.objects.get_or_create(valeur="150 cl")[0], contenance=Decimal("1.5"), unite_contenance="L",
            unite_vente=UniteVenteArticle.objects.get_or_create(nom="Pack de 6")[0],
        )
        fuite = PerteEau.objects.create(usine=self.usine, date=jour(4), cause="FUITE", volume_estime_m3=2)
        self.assertEqual(fuite.type_perte, "ANORMALE")
        rinçage = PerteEau.objects.create(usine=self.usine, date=jour(5), cause="RINCAGE_BOUTEILLES", article=format_15, nombre_bouteilles=1000)
        self.assertEqual((rinçage.type_perte, rinçage.volume_m3), ("NORMALE", Decimal("1.5")))
        for champs in ({"cause": "FUITE", "type_perte": "NORMALE", "volume_estime_m3": 1}, {"cause": "AUTRE", "volume_estime_m3": 1, "commentaire": "x"},
                       {"cause": "AUTRE", "type_perte": "NORMALE", "volume_estime_m3": 1}, {"cause": "CASSE"},
                       {"cause": "CASSE", "volume_estime_m3": 1, "nombre_bouteilles": 10}, {"cause": "CASSE", "nombre_bouteilles": 10}):
            with self.assertRaises(ValidationError, msg=champs):
                PerteEau.objects.create(usine=self.usine, date=jour(6), **champs)
        self.assertEqual(synthese_mois(self.usine, NOVEMBRE)["pertes"], {"normales_m3": "1.5", "anormales_m3": "2", "declarations": 2})

    def test_droits_des_saisies(self):
        donnees = {"compteur": self.debit_eau.pk, "date": str(timezone.localdate()), "index": "100"}
        self.assertEqual(self.client_pour(Profil.CONTROLE_GESTION).post("/api/eau/releves-compteurs/", donnees, format="json").status_code, 403)
        reponse = self.technicien.post("/api/eau/releves-compteurs/", donnees, format="json")
        self.assertEqual(reponse.status_code, 201, reponse.content)
        self.assertEqual(reponse.data["saisi_par_nom"], "technicien_eau")
        perte = {"usine": self.usine.pk, "date": str(timezone.localdate()), "cause": "CASSE", "volume_estime_m3": "0.5"}
        reponse = self.client_pour(Profil.AGENT_PRODUCTION).post("/api/eau/pertes/", perte, format="json")
        self.assertEqual((reponse.status_code, reponse.data.get("type_perte")), (201, "ANORMALE"))
        url = f"/api/eau/traitement/synthese/?usine={self.usine.pk}&mois={self.courant}"
        for profil in (Profil.TECHNICIEN_EAU, Profil.CONTROLE_GESTION, Profil.COMPTABILITE_DAF):
            self.assertEqual(self.client_pour(profil).get(url).status_code, 200)
        self.assertEqual(self.client_pour(Profil.CAISSIER).get(url).status_code, 403)
