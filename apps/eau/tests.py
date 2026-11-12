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


# =====================================================================
# Phase 4 - maintenance
# =====================================================================

from apps.core.models import Notification  # noqa: E402
from apps.eau.maintenance import Statut, echeances_preventives, envoyer_alertes, fins_de_vie, intervalle_jours  # noqa: E402
from apps.eau.models import AlerteEnvoyee, Installation, Intervention  # noqa: E402


class BaseMaintenance(BaseEau):
    def setUp(self):
        super().setUp()
        etape = lambda code: EtapeStandard.objects.get(code=code)
        self.membrane = Equipement.objects.create(designation="Membrane DP1", type_equipement="TRAITEMENT", usine=self.usine, poste=self.poste_uf)
        self.dp1 = ElementCout.objects.create(
            usine=self.usine, libelle="Membrane DP1", etape=etape("ULTRAFILTRATION"), equipement=self.membrane,
            famille="ETALEE", categorie="DUREE_DE_VIE", unite="unité",
        )
        VersionElementCout.objects.create(element=self.dp1, mois_application="2025-01", quantite=1, prix_unitaire=1000000, duree_vie_mois=48)
        self.entretien = ElementCout.objects.create(
            usine=self.usine, libelle="Entretien préventif pompe du forage", etape=etape("CAPTAGE"), equipement=self.pompe_forage,
            famille="PREVENTIVE", categorie="MAINTENANCE_PREVENTIVE", unite="intervention",
        )
        VersionElementCout.objects.create(element=self.entretien, mois_application="2025-01", quantite=1, prix_unitaire=120000, frequence=3, periode="AN")
        self.panne = ElementCout.objects.create(
            usine=self.usine, libelle="Réparations UF", etape=etape("ULTRAFILTRATION"), famille="AU_BESOIN", categorie="MAINTENANCE_AU_BESOIN",
        )

    def intervenir(self, type_intervention, le, **champs):
        equipement = champs.pop("equipement", self.pompe_forage if type_intervention == "PREVENTIVE" else self.membrane)
        return Intervention.objects.create(
            equipement=equipement, type_intervention=type_intervention, date=le, description="Intervention test", **champs,
        )

    def lot_dp1(self, mois="2025-01", **champs):
        valeurs = {"quantite": 1, "prix_unitaire": 1000000, "duree_vie_mois": 48, **champs}
        return Installation.objects.create(element=self.dp1, mois_installation=mois, **valeurs)


class MaintenanceTests(BaseMaintenance):

    def test_intervalle_entre_deux_operations(self):
        self.assertEqual(intervalle_jours(3, Periode.AN), 122)
        self.assertEqual(intervalle_jours(2, Periode.MOIS), 15)
        self.assertEqual(intervalle_jours(1, Periode.SEMAINE), 7)
        self.assertEqual(intervalle_jours(4, Periode.JOUR), 1)

    def test_remplacement_anticipe_de_la_membrane_dp1_scenario_mois_3(self):
        """Onglet « Scénario 3 mois » : 1 000 000 x (48 - 12) ÷ 48 = 750 000 ; étalement +2 083,33 au mois du remplacement."""
        ancien = self.lot_dp1("2025-01")
        remplacement = self.intervenir("REMPLACEMENT", date(2026, 1, 15), element_remplace=self.dp1)
        self.assertEqual(remplacement.quantite_remplacee, 1)
        nouveau = self.lot_dp1("2026-01", prix_unitaire=1100000, remplace=ancien, intervention=remplacement)
        self.assertEqual(nouveau.mois_deja_etales, 12)
        self.assertEqual(nouveau.valeur_residuelle, Decimal(750000))
        self.assertEqual(ancien.montant_etale("2025-12").quantize(CENTIME), Decimal("20833.33"))
        self.assertEqual(ancien.montant_etale("2026-01"), 0)        # sa part du mois est dans la valeur résiduelle
        self.assertEqual(nouveau.montant_etale("2025-12"), 0)
        self.assertEqual(nouveau.montant_etale("2026-01").quantize(CENTIME), Decimal("22916.67"))
        variation = nouveau.montant_etale("2026-01") - ancien.montant_etale("2025-12")
        self.assertEqual(variation.quantize(CENTIME), Decimal("2083.33"))
        # Étalé jusqu'au bout de sa durée de vie, puis plus rien.
        self.assertEqual(nouveau.dernier_mois, "2029-12")
        self.assertEqual(nouveau.montant_etale("2030-01"), 0)

    def test_remplacement_apres_la_fin_de_vie_sans_valeur_residuelle(self):
        ancien = self.lot_dp1("2020-01")
        self.assertEqual(self.lot_dp1("2025-03", remplace=ancien).valeur_residuelle, 0)

    def test_remplacement_partiel_d_un_lot(self):
        lampes = ElementCout.objects.create(
            usine=self.usine, libelle="Lampes UV", etape=EtapeStandard.objects.get(code="UV"), famille="ETALEE", categorie="DUREE_DE_VIE",
        )
        lot = Installation.objects.create(element=lampes, mois_installation="2025-01", quantite=2, prix_unitaire=120000, duree_vie_mois=12)
        neuve = Installation.objects.create(element=lampes, mois_installation="2025-07", quantite=1, prix_unitaire=130000, duree_vie_mois=12, remplace=lot)
        self.assertEqual(neuve.valeur_residuelle, Decimal(60000))   # 120 000 x 1 x 6 ÷ 12
        self.assertEqual(lot.quantite_en_place("2025-07"), 1)
        self.assertEqual(lot.montant_etale("2025-07"), Decimal(10000))
        with self.assertRaises(ValidationError):   # il ne reste qu'une lampe dans l'ancien lot
            Installation.objects.create(element=lampes, mois_installation="2025-08", quantite=2, prix_unitaire=1, duree_vie_mois=12, remplace=lot)

    def test_regles_des_lots(self):
        ancien = self.lot_dp1("2025-01")
        with self.assertRaises(ValidationError):   # pas un élément étalé
            Installation.objects.create(element=self.entretien, mois_installation="2025-01", quantite=1, prix_unitaire=1, duree_vie_mois=1)
        with self.assertRaises(ValidationError):   # remplacement avant l'installation de l'ancien lot
            self.lot_dp1("2025-01", remplace=ancien)
        remplacement = self.intervenir("REMPLACEMENT", date(2026, 1, 15), element_remplace=self.dp1)
        with self.assertRaises(ValidationError):   # pas le mois de l'intervention
            self.lot_dp1("2026-02", remplace=ancien, intervention=remplacement)
        with self.assertRaises(ValidationError):   # intervention sans lot remplacé
            self.lot_dp1("2026-01", intervention=remplacement)
        self.lot_dp1("2026-01", remplace=ancien, intervention=remplacement)
        ancien.prix_unitaire = 900000
        with self.assertRaises(ValidationError):   # lot déjà remplacé : figé
            ancien.save()
        with self.assertRaises(ValidationError):
            ancien.delete()
        with self.assertRaises(ValidationError):   # sa nouvelle pièce est enregistrée
            remplacement.delete()

    def test_regles_des_interventions(self):
        with self.assertRaises(ValidationError):   # préventive sans opération du plan
            self.intervenir("PREVENTIVE", date(2025, 3, 1))
        with self.assertRaises(ValidationError):   # l'opération n'est pas préventive
            self.intervenir("PREVENTIVE", date(2025, 3, 1), operation=self.dp1)
        with self.assertRaises(ValidationError):   # opération d'un autre équipement
            self.intervenir("PREVENTIVE", date(2025, 3, 1), operation=self.entretien, equipement=self.pompe_uf)
        with self.assertRaises(ValidationError):   # soutireuse : hors coût de l'eau
            self.intervenir("AU_BESOIN", date(2025, 3, 1), equipement=self.soutireuse)
        with self.assertRaises(ValidationError):   # remplacement sans pièce
            self.intervenir("REMPLACEMENT", date(2025, 3, 1))
        with self.assertRaises(ValidationError):   # pièce remplacée sur une réparation
            self.intervenir("AU_BESOIN", date(2025, 3, 1), element_remplace=self.dp1)
        with self.assertRaises(ValidationError):   # date future
            self.intervenir("AU_BESOIN", timezone.localdate() + timedelta(days=1))
        self.intervenir("AU_BESOIN", date(2025, 3, 1), equipement=self.pompe_uf)

    def test_echeances_de_la_maintenance_preventive(self):
        """3 fois par an = tous les 122 jours, depuis le début du plan (01/01/2025) puis depuis la dernière intervention."""
        statut = lambda jour: {l["libelle"]: (l["prochaine_echeance"], l["statut"]) for l in echeances_preventives(self.usine, jour)}
        cle = self.entretien.libelle
        self.assertEqual(statut(date(2025, 4, 1))[cle], ("2025-05-03", Statut.A_VENIR))
        self.assertEqual(statut(date(2025, 4, 28))[cle], ("2025-05-03", Statut.A_FAIRE))
        self.assertEqual(statut(date(2025, 5, 10))[cle], ("2025-05-03", Statut.EN_RETARD))
        self.intervenir("PREVENTIVE", date(2025, 5, 10), operation=self.entretien)
        self.assertEqual(statut(date(2025, 5, 10))[cle], ("2025-09-09", Statut.A_VENIR))
        # Opération retirée du plan : plus d'échéance.
        VersionElementCout.objects.create(element=self.entretien, mois_application=self.suivant, retire=True)
        annee, numero = (int(x) for x in self.suivant.split("-"))
        self.assertNotIn(cle, statut(date(annee, numero, 1)))

    def test_fin_de_vie(self):
        Installation.objects.create(
            element=ElementCout.objects.create(usine=self.usine, libelle="Charbon actif", etape=EtapeStandard.objects.get(code="PREFILTRATION"),
                                               famille="ETALEE", categorie="DUREE_DE_VIE"),
            mois_installation="2025-01", quantite=200, prix_unitaire=3000, duree_vie_mois=12,
        )
        statut = lambda jour: {l["libelle"]: l["statut"] for l in fins_de_vie(self.usine, jour)}
        self.assertEqual(statut(date(2025, 11, 30))["Charbon actif"], Statut.EN_SERVICE)
        self.assertEqual(statut(date(2025, 12, 1))["Charbon actif"], Statut.FIN_DE_VIE_PROCHE)
        self.assertEqual(statut(date(2026, 1, 1))["Charbon actif"], Statut.FIN_DE_VIE_DEPASSEE)

    def test_alertes_envoyees_une_seule_fois(self):
        for profil in (Profil.TECHNICIEN_EAU, Profil.CONTROLE_GESTION, Profil.COMPTABILITE_DAF):
            Utilisateur.objects.create_user(profil.lower(), password="x", profil=profil)
        self.lot_dp1("2025-01", duree_vie_mois=12)
        recues = lambda: Notification.objects.filter(destinataire__profil=Profil.TECHNICIEN_EAU).count()
        self.assertEqual(envoyer_alertes(date(2025, 4, 1)), 0)
        self.assertEqual(envoyer_alertes(date(2025, 4, 28)), 1)    # 7 jours avant
        self.assertEqual(envoyer_alertes(date(2025, 4, 29)), 0)    # déjà envoyée
        self.assertEqual(envoyer_alertes(date(2025, 5, 3)), 1)     # à l'échéance
        self.assertEqual(envoyer_alertes(date(2025, 12, 1)), 1)    # toujours en retard (déjà signalé) ; fin de vie de la membrane
        self.assertEqual(envoyer_alertes(date(2025, 12, 2)), 0)
        self.assertEqual(recues(), 3)
        self.assertEqual(Notification.objects.filter(destinataire__profil=Profil.CONTROLE_GESTION).count(), 3)
        self.assertEqual(Notification.objects.filter(destinataire__profil=Profil.COMPTABILITE_DAF).count(), 0)
        self.assertEqual(AlerteEnvoyee.objects.count(), 3)

    def test_reparation_et_remplacement_notifient_controle_de_gestion_et_comptabilite(self):
        for profil in (Profil.TECHNICIEN_EAU, Profil.CONTROLE_GESTION, Profil.COMPTABILITE_DAF):
            Utilisateur.objects.create_user(profil.lower(), password="x", profil=profil)
        self.intervenir("PREVENTIVE", date(2025, 3, 1), operation=self.entretien)
        self.assertFalse(Notification.objects.exists())
        self.intervenir("AU_BESOIN", date(2025, 3, 2), equipement=self.pompe_uf)
        self.intervenir("REMPLACEMENT", date(2025, 3, 3), element_remplace=self.dp1)
        for profil in (Profil.CONTROLE_GESTION, Profil.COMPTABILITE_DAF):
            self.assertEqual(Notification.objects.filter(destinataire__profil=profil).count(), 2)
        self.assertFalse(Notification.objects.filter(destinataire__profil=Profil.TECHNICIEN_EAU).exists())

    def test_droits_et_api(self):
        technicien = self.client_pour(Profil.TECHNICIEN_EAU)
        controle = self.client_pour(Profil.CONTROLE_GESTION)
        reponse = technicien.post("/api/eau/interventions/", {
            "equipement": self.membrane.pk, "type_intervention": "REMPLACEMENT", "date": "2026-01-15",
            "description": "Membrane abîmée", "element_remplace": self.dp1.pk,
        }, format="json")
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertFalse(reponse.data["nouvelle_piece_enregistree"])
        self.assertEqual(controle.post("/api/eau/interventions/", {}, format="json").status_code, 403)
        # Les lots portent les prix : pas les techniciens.
        self.assertEqual(technicien.get("/api/eau/installations/").status_code, 403)
        ancien = self.lot_dp1("2025-01")
        reponse = controle.post("/api/eau/installations/", {
            "element": self.dp1.pk, "quantite": 1, "prix_unitaire": 1100000, "duree_vie_mois": 48,
            "mois_installation": "2026-01", "remplace": ancien.pk, "intervention": Intervention.objects.get().pk,
        }, format="json")
        self.assertEqual(reponse.status_code, 201, reponse.data)
        self.assertEqual((reponse.data["valeur_residuelle"], reponse.data["montant_etale_mensuel"]), ("750000.00", "22916.67"))
        # Échéances : consultables par les techniciens, sans aucun prix.
        reponse = technicien.get(f"/api/eau/maintenance/echeances/?usine={self.usine.pk}")
        self.assertEqual(reponse.status_code, 200)
        self.assertNotIn("prix", str(reponse.data))
        self.assertEqual([l["libelle"] for l in reponse.data["preventive"]], [self.entretien.libelle])
        self.assertEqual(technicien.get("/api/eau/maintenance/echeances/").status_code, 400)


# =====================================================================
# Phase 5 - coût réel et clôture (onglet « Scénario 3 mois »)
# =====================================================================

from apps.couts.models import Charge, CoutReel, NatureCout, VolumeEauSite  # noqa: E402
from apps.eau.calculs import CalculImpossible as CalculImpossibleReel  # noqa: E402
from apps.eau.maintenance import envoyer_alertes as envoyer_alertes_eau  # noqa: E402
from apps.eau.models import ClotureMoisEau, ValidationSansImputation, ValorisationEauOF  # noqa: E402
from apps.eau.reel import calcul_reel, cloturer  # noqa: E402
from apps.production.models import OrdreFabrication, SuiviEau  # noqa: E402

MOIS = "2025-11"   # 30 jours, 25 jours du lundi au samedi : 720 h et 200 h comme le classeur
ATTENDUES = ("Électricité pompe du forage", "Entretien préventif pompe du forage", "Sel de régénération",
             "Produit de lavage des filtres", "Analyses par laboratoire externe", "Kits de contrôle interne")


class BaseScenario(BaseClasseur):
    def setUp(self):
        super().setUp()
        # Paramétrage applicable depuis janvier 2025.
        for modele in (VersionElementCout, PrevisionVolume, PrevisionCaptage):
            modele.objects.update(mois_application="2025-01")
        ParametresEau.objects.create(usine=self.usine, mois_application="2025-01", taux_rejet_tolere_pct=2, seuil_grosse_reparation=500000)
        CoutStandardEau.objects.create(
            usine=self.usine, mois_application="2025-01", statut="VALIDE", volume_m3=200, cout_forage=196000,
            cout_traitement=627000, cout_mensuel=823000, cout_m3=4115,
        )
        ElementCout.objects.filter(usine=self.usine, libelle__in=ATTENDUES).update(attendue_chaque_mois=True)
        self.elements = {element.libelle: element for element in ElementCout.objects.filter(usine=self.usine)}
        # Équipements et heures (partie B) : forage sur sa ligne, le reste sur la ligne de traitement.
        etape = lambda code: EtapeStandard.objects.get(code=code)
        ligne = self.poste_uf.ligne
        self.pompe_forage.poste = Poste.objects.create(
            ligne=Ligne.objects.create(designation="Forage", usine=self.usine, activite=ligne.activite), etape=etape("CAPTAGE"),
        )
        self.pompe_forage.save()
        pompe_filtres = Equipement.objects.create(designation="Pompe d'alimentation des filtres", type_equipement="POMPE", usine=self.usine,
                                                  poste=Poste.objects.create(ligne=ligne, etape=etape("PREFILTRATION")))
        lampe_uv = Equipement.objects.create(designation="Lampe UV", type_equipement="TRAITEMENT", usine=self.usine,
                                             poste=Poste.objects.create(ligne=ligne, etape=etape("UV")))
        for equipement, kw, heures, jours in ((self.pompe_forage, 5, 24, "TOUS"), (pompe_filtres, 2, 8, "LUNDI_SAMEDI"),
                                              (self.pompe_uf, 3, 8, "LUNDI_SAMEDI"), (lampe_uv, "0.1", 8, "LUNDI_SAMEDI"),
                                              (self.soutireuse, 10, 8, "LUNDI_SAMEDI")):
            CaracteristiquesEquipement.objects.create(equipement=equipement, mois_application="2025-01", puissance_kw=Decimal(str(kw)),
                                                      heures_marche_jour=heures, jours_de_marche=jours)
        self.ligne = ligne
        self.site_jus = Usine.objects.create(nom="Site jus scénario")
        self.debitmetres = {
            site: Compteur.objects.create(code=f"D-{site.pk}", libelle="Débitmètre", type_compteur="DEBITMETRE", usine=self.usine, site_desservi=site)
            for site in (self.usine, self.site_jus)
        }
        self.nature = NatureCout.objects.create(libelle="Charges du site eau", inducteur="VOLUME_EAU_M3")
        self.responsable = Utilisateur.objects.create_user("resp_prod", password="x", profil=Profil.RESPONSABLE_PRODUCTION)

    # -- saisies du scénario ------------------------------------------------
    def capter(self, site_eau, autres):
        for site, volume in ((self.usine, site_eau), (self.site_jus, autres)):
            ReleveCompteur.objects.create(compteur=self.debitmetres[site], date=date(2025, 10, 31), index=1000)
            ReleveCompteur.objects.create(compteur=self.debitmetres[site], date=date(2025, 11, 30), index=1000 + volume)

    def produire(self, conformes_15, conformes_05, conformes_5, rejetees_15):
        # OF déjà clôturés (créés directement : la recette et le déroulé de production ne sont pas l'objet du test).
        fin = timezone.make_aware(timezone.datetime(2025, 11, 28, 17))
        OrdreFabrication.objects.bulk_create([
            OrdreFabrication(numero=f"OF-EAU-{nom}", article=self.formats[nom], quantite_a_produire=bouteilles,
                             responsable=self.responsable, statut="CLOTURE", ligne=self.ligne, date_fin=fin)
            for nom, bouteilles in (("150 cl", conformes_15), ("50 cl", conformes_05), ("500 cl", conformes_5))
        ])
        ofs = [OrdreFabrication.objects.get(numero=f"OF-EAU-{nom}") for nom in ("150 cl", "50 cl", "500 cl")]
        SuiviEau.objects.bulk_create([SuiviEau(
            ordre_fabrication=ofs[0], volume_capte_l=0, volume_obtenu_traitement_l=0, volume_envoye_embouteillage_l=0,
            bouteilles_produites=conformes_15 + rejetees_15, bouteilles_conformes=conformes_15, bouteilles_rejetees=rejetees_15,
        )])
        return ofs

    def imputer(self, libelle, montant, **champs):
        return Charge.objects.create(nature=self.nature, periode=MOIS, montant=montant, element_eau=self.elements[libelle], **champs)

    def sans_imputation(self, libelle, motif="Aucun entretien ce mois"):
        return ValidationSansImputation.objects.create(element=self.elements[libelle], mois=MOIS, motif=motif)

    def charges_courantes(self, electricite, sel, entretien=None):
        self.imputer("Électricité pompe du forage", electricite, source="Facture d'électricité du site")
        if entretien:
            self.imputer("Entretien préventif pompe du forage", entretien, equipement=self.pompe_forage)
        else:
            self.sans_imputation("Entretien préventif pompe du forage")
        self.imputer("Sel de régénération", sel)
        self.imputer("Produit de lavage des filtres", 20000)
        self.imputer("Analyses par laboratoire externe", 100000)
        self.imputer("Kits de contrôle interne", 43000)

    def mois_1(self):
        self.capter(220, 330)
        ofs = self.produire(100000, 60000, 4000, 1000)
        self.charges_courantes(500000, 60000, entretien=120000)
        return ofs


class CoutReelTests(BaseScenario):

    def test_mois_1_normal(self):
        self.mois_1()
        calcul = calcul_reel(self.usine, MOIS)
        self.assertEqual(calcul["bloquants"], [])
        self.assertEqual(calcul["volumes"]["volume_m3"], "200")
        self.assertEqual(calcul["volumes"]["part_site_eau"], "0.4")
        self.assertEqual(calcul["volumes"]["taux_pertes_site"], "0.090909")
        rejet = next(f for f in calcul["volumes"]["formats"] if f["article"] == self.formats["150 cl"].code)
        self.assertEqual((rejet["taux_rejet"], rejet["classement_rejet"], rejet["eau_rejetee_m3"]), ("0.009901", "Perte normale", "1.5"))
        self.assertEqual(calcul["electricite"], {
            "facture_site": "500000.00", "total_kw_heures": "6620", "part_forage": "271903.32",
            "part_traitement": "77039.27", "part_production_hors_eau": "151057.40",
        })
        self.assertEqual(calcul["synthese"], {
            "cout_forage_avant_partage": "491903.32", "cout_forage_site_eau": "196761.33", "cout_forage_autres_sites": "295141.99",
            "cout_traitement": "591705.94", "cout_reel_courant": "788467.27", "charges_au_besoin": "0.00",
            "charges_exceptionnelles": "0.00", "cout_reel_total": "788467.27", "cout_m3": "3942.34", "cout_m3_courant": "3942.34",
            "cout_standard_m3": "4115.00", "eau_valorisee_of": "823000.00", "ecart_du_mois": "-34532.73",
            "valeur_perte_anormale": "0.00", "ecart_total_pct": "-4.2", "ecart_courant_pct": "-4.2",
        })
        self.assertEqual({l["statut"] for l in calcul["charges_attendues"]}, {"IMPUTEE"})

    def test_mois_2_panne_de_la_pompe_uf_et_production_reduite(self):
        self.capter(180, 360)
        self.produire(85000, 50000, 3000, 3000)
        ExceptionHeures.objects.create(ligne=self.ligne, date=date(2025, 11, 12), heures_en_moins=8, motif="PANNE")
        ExceptionHeures.objects.create(ligne=self.ligne, date=date(2025, 11, 13), heures_en_moins=8, motif="PANNE")
        ExceptionHeures.objects.create(ligne=self.ligne, date=date(2025, 11, 14), heures_en_moins=4, motif="PANNE")
        self.charges_courantes(450000, 55000)
        self.imputer("Réparation pompe de l'ultrafiltration", 300000, equipement=self.pompe_uf)
        calcul = calcul_reel(self.usine, MOIS)
        self.assertEqual(calcul["bloquants"], [])
        self.assertEqual(calcul["electricite"]["total_kw_heures"], "6318")
        self.assertEqual(calcul["electricite"]["part_forage"], "256410.26")
        rejet = next(f for f in calcul["volumes"]["formats"] if f["article"] == self.formats["150 cl"].code)
        self.assertEqual((rejet["taux_rejet"], rejet["classement_rejet"]), ("0.034091", "Perte anormale"))
        synthese = calcul["synthese"]
        attendu = {
            "cout_forage_avant_partage": "356410.26", "cout_forage_site_eau": "118803.42", "cout_traitement": "575051.28",
            "cout_reel_courant": "693854.70", "charges_au_besoin": "300000.00", "cout_reel_total": "993854.70",
            "cout_m3": "5933.46", "cout_m3_courant": "4142.42", "eau_valorisee_of": "689262.50", "ecart_du_mois": "304592.20",
            "valeur_perte_anormale": "18517.50", "ecart_total_pct": "44.19", "ecart_courant_pct": "0.67",
        }
        self.assertEqual({cle: synthese[cle] for cle in attendu}, attendu)
        statuts = {l["libelle"]: l["statut"] for l in calcul["charges_attendues"]}
        self.assertEqual(statuts["Entretien préventif pompe du forage"], "VALIDEE_SANS_IMPUTATION")

    def test_mois_3_remplacement_anticipe_de_la_membrane_dp1(self):
        self.capter(225, 300)
        self.produire(100000, 60000, 4000, 1000)
        self.charges_courantes(500000, 62000)
        dp1 = self.elements["Membrane DP1 (0,01 µ)"]
        ancien = Installation.objects.create(element=dp1, mois_installation="2024-11", quantite=1, prix_unitaire=1000000, duree_vie_mois=48)
        remplacement = Intervention.objects.create(equipement=self.pompe_uf, type_intervention="REMPLACEMENT", date=date(2025, 11, 15),
                                                   description="Membrane DP1 abîmée", element_remplace=dp1)
        Installation.objects.create(element=dp1, mois_installation=MOIS, quantite=1, prix_unitaire=1100000, duree_vie_mois=48,
                                    remplace=ancien, intervention=remplacement)
        synthese = calcul_reel(self.usine, MOIS)["synthese"]
        attendu = {
            "cout_forage_avant_partage": "371903.32", "cout_forage_site_eau": "159387.14", "cout_traitement": "595789.27",
            "cout_reel_courant": "755176.41", "charges_exceptionnelles": "750000.00", "cout_reel_total": "1505176.41",
            "cout_m3": "7525.88", "cout_m3_courant": "3775.88", "ecart_du_mois": "682176.41",
            "ecart_total_pct": "82.89", "ecart_courant_pct": "-8.24",
        }
        self.assertEqual({cle: synthese[cle] for cle in attendu}, attendu)

    def test_grosse_reparation_etalee_et_regles_des_imputations(self):
        self.mois_1()
        reparation = self.elements["Réparation pompe de l'ultrafiltration"]
        with self.assertRaises(ValidationError):   # réparation sans équipement
            self.imputer("Réparation pompe de l'ultrafiltration", 100000)
        with self.assertRaises(ValidationError):   # sous le seuil de grosse réparation : pas d'étalement
            self.imputer("Réparation pompe de l'ultrafiltration", 400000, equipement=self.pompe_uf, duree_etalement_eau_mois=12)
        with self.assertRaises(ValidationError):   # une charge étalée ne s'impute pas
            self.imputer("Charbon actif", 600000)
        with self.assertRaises(ValidationError):   # seule une réparation s'étale
            self.imputer("Sel de régénération", 600000, duree_etalement_eau_mois=12)
        Charge.objects.create(nature=self.nature, periode=MOIS, montant=600000, element_eau=reparation,
                              equipement=self.pompe_uf, duree_etalement_eau_mois=12)
        self.assertEqual(calcul_reel(self.usine, MOIS)["synthese"]["charges_au_besoin"], "50000.00")
        self.assertEqual(calcul_reel(self.usine, "2026-10")["synthese"]["charges_au_besoin"], "50000.00")
        self.assertEqual(calcul_reel(self.usine, "2026-11")["synthese"]["charges_au_besoin"], "0.00")


class ClotureTests(BaseScenario):

    def test_cloture_valorise_les_of_et_fige_le_mois(self):
        ofs = self.mois_1()
        cloture = cloturer(self.usine, MOIS)
        self.assertEqual((cloture.cout_reel_total, cloture.cout_m3, cloture.valorisation_of, cloture.ecart),
                         (Decimal("788467.27"), Decimal("3942.3364"), Decimal("823000.00"), Decimal("-34532.73")))
        valorisation = ValorisationEauOF.objects.get(ordre_fabrication=ofs[0])
        self.assertEqual((valorisation.volume_m3, valorisation.montant_eau, valorisation.electricite_production),
                         (Decimal("150.000"), Decimal("617250.00"), Decimal("113293.05")))
        self.assertEqual(sum(v.montant_eau for v in ValorisationEauOF.objects.all()), Decimal("823000.00"))
        self.assertEqual(CoutReel.objects.get(ordre_fabrication=ofs[0]).cout_eau, Decimal("730543.05"))
        # Les volumes des débitmètres alimentent la clé du forage du module Coûts.
        self.assertEqual({v.usine_id: v.volume_m3 for v in VolumeEauSite.objects.filter(periode=MOIS)},
                         {self.usine.pk: Decimal("220.000"), self.site_jus.pk: Decimal("330.000")})
        # Le mois est figé.
        with self.assertRaises(ValidationError):
            self.imputer("Sel de régénération", 1000)
        charge = Charge.objects.get(element_eau=self.elements["Sel de régénération"])
        charge.montant = 70000
        with self.assertRaises(ValidationError):
            charge.save()
        with self.assertRaises(ValidationError):
            charge.delete()
        with self.assertRaises(ValidationError):
            ReleveCompteur.objects.create(compteur=self.debitmetres[self.usine], date=date(2025, 11, 15), index=1100)
        with self.assertRaises(ValidationError):
            ExceptionHeures.objects.create(ligne=self.ligne, date=date(2025, 11, 12), heures_en_moins=2, motif="PANNE")
        with self.assertRaises(ValidationError):
            cloture.delete()
        with self.assertRaises(CalculImpossibleReel):
            cloturer(self.usine, MOIS)
        # Le résultat conservé ne change plus.
        self.assertEqual(ClotureMoisEau.objects.get().resultat["synthese"]["cout_reel_total"], "788467.27")

    def test_cloture_refusee_si_charge_attendue_manquante_ou_mois_en_cours(self):
        self.capter(220, 330)
        self.produire(100000, 60000, 4000, 1000)
        self.imputer("Électricité pompe du forage", 500000)
        with self.assertRaises(CalculImpossibleReel) as erreur:
            cloturer(self.usine, MOIS)
        self.assertIn("Sel de régénération", str(erreur.exception))
        with self.assertRaises(CalculImpossibleReel):
            cloturer(self.usine, mois_courant())
        with self.assertRaises(ValidationError):   # déjà imputée : pas de validation sans imputation
            self.sans_imputation("Électricité pompe du forage")
        with self.assertRaises(ValidationError):   # motif obligatoire
            self.sans_imputation("Sel de régénération", motif=" ")

    def test_les_mois_se_cloturent_dans_l_ordre(self):
        self.mois_1()
        cloturer(self.usine, MOIS)
        with self.assertRaises(CalculImpossibleReel) as erreur:
            cloturer(self.usine, "2026-01")
        self.assertIn("2025-12", str(erreur.exception))

    def test_alerte_charge_attendue_cinq_jours_avant_la_limite(self):
        Utilisateur.objects.create_user("compta", password="x", profil=Profil.COMPTABILITE_DAF)
        self.imputer("Électricité pompe du forage", 500000)
        signalees = lambda: Notification.objects.filter(titre__startswith="Charge attendue", destinataire__profil=Profil.COMPTABILITE_DAF).count()
        envoyer_alertes_eau(date(2025, 12, 4))     # limite le 10/12 : trop tôt
        self.assertEqual(signalees(), 0)
        envoyer_alertes_eau(date(2025, 12, 5))     # 5 manquantes (l'électricité est imputée), signalées une seule fois
        envoyer_alertes_eau(date(2025, 12, 6))
        self.assertEqual(signalees(), 5)

    def test_api(self):
        self.mois_1()
        controle = self.client_pour(Profil.CONTROLE_GESTION)
        self.assertEqual(self.client_pour(Profil.TECHNICIEN_EAU).get(f"/api/eau/reel/calcul/?usine={self.usine.pk}&mois={MOIS}").status_code, 403)
        reponse = controle.get(f"/api/eau/reel/calcul/?usine={self.usine.pk}&mois={MOIS}")
        self.assertEqual((reponse.status_code, reponse.data["synthese"]["cout_reel_total"], reponse.data["cloture"]), (200, "788467.27", None))
        reponse = self.client_pour(Profil.COMPTABILITE_DAF).get(f"/api/eau/reel/charges-attendues/?usine={self.usine.pk}&mois={MOIS}")
        self.assertEqual((reponse.data["date_limite"], len(reponse.data["charges"])), ("2025-12-10", 6))
        self.assertEqual(self.client_pour(Profil.COMPTABILITE_DAF).post("/api/eau/clotures/cloturer/", {"usine": self.usine.pk, "mois": MOIS}, format="json").status_code, 403)
        reponse = controle.post("/api/eau/clotures/cloturer/", {"usine": self.usine.pk, "mois": MOIS}, format="json")
        self.assertEqual((reponse.status_code, reponse.data["cout_reel_total"]), (201, "788467.27"))
        self.assertEqual(controle.post("/api/eau/clotures/cloturer/", {"usine": self.usine.pk, "mois": MOIS}, format="json").status_code, 400)
        reponse = controle.get(f"/api/eau/reel/calcul/?usine={self.usine.pk}&mois={MOIS}")
        self.assertIsNotNone(reponse.data["cloture"])
        self.assertEqual(len(controle.get("/api/eau/valorisations-of/").data["results"] if isinstance(controle.get("/api/eau/valorisations-of/").data, dict) else controle.get("/api/eau/valorisations-of/").data), 3)


class CoutReelOFTests(BaseScenario):
    """Après la clôture, le coût réel de l'OF prend l'eau au standard à la place des charges amont de la cascade."""

    def test_charges_amont_remplacees_par_l_eau_au_standard(self):
        from apps.couts.models import RepartitionCout
        of = self.mois_1()[0]
        amont = Charge.objects.create(nature=NatureCout.objects.create(
            libelle="Traitement (cascade)", etape=EtapeStandard.objects.get(code="UV"), inducteur="VOLUME_EAU_M3"), periode=MOIS, montant=1000)
        aval = Charge.objects.create(nature=NatureCout.objects.create(
            libelle="Soutirage (cascade)", etape=self.poste_remplissage.etape, inducteur="BOUTEILLES"), periode=MOIS, montant=400)
        for charge in (amont, aval, Charge.objects.get(element_eau=self.elements["Sel de régénération"])):
            RepartitionCout.objects.create(charge=charge, niveau="PRODUIT", ordre_fabrication=of, article=of.article,
                                           inducteur=charge.nature.inducteur, quote_part=1, montant=charge.montant, statut="REPARTI")
        cout = CoutReel.objects.create(ordre_fabrication=of).calculer()
        self.assertEqual((cout.cout_charges_reparties, cout.cout_eau), (Decimal("61400.00"), 0))
        cloturer(self.usine, MOIS)
        cout.refresh_from_db()
        self.assertEqual((cout.cout_charges_reparties, cout.cout_eau), (Decimal("400.00"), Decimal("730543.05")))
        self.assertEqual(cout.cout_total, Decimal("730943.05"))


# =====================================================================
# Phase 6 - révision du standard (décision après la clôture)
# =====================================================================

from apps.eau.revision import evolution  # noqa: E402


class RevisionTests(BaseScenario):

    def mois_3(self):
        self.capter(225, 300)
        self.produire(100000, 60000, 4000, 1000)
        self.charges_courantes(500000, 62000)
        dp1 = self.elements["Membrane DP1 (0,01 µ)"]
        ancien = Installation.objects.create(element=dp1, mois_installation="2024-11", quantite=1, prix_unitaire=1000000, duree_vie_mois=48)
        remplacement = Intervention.objects.create(equipement=self.pompe_uf, type_intervention="REMPLACEMENT", date=date(2025, 11, 15),
                                                   description="Membrane DP1 abîmée", element_remplace=dp1)
        Installation.objects.create(element=dp1, mois_installation=MOIS, quantite=1, prix_unitaire=1100000, duree_vie_mois=48,
                                    remplace=ancien, intervention=remplacement)

    def test_mois_1_standard_maintenu(self):
        self.mois_1()
        cloture = cloturer(self.usine, MOIS)
        self.assertEqual((cloture.decision, cloture.ecart_courant_pct, cloture.standard_propose), ("MAINTENU", Decimal("-4.1960"), None))
        self.assertEqual(cloture.volume_prevu_m3, Decimal("200.000"))

    def test_mois_2_une_panne_ne_change_pas_le_standard(self):
        """Écart total +44 % (panne), mais hors charges au besoin +0,67 % : standard maintenu."""
        self.capter(180, 360)
        self.produire(85000, 50000, 3000, 3000)
        ExceptionHeures.objects.create(ligne=self.ligne, date=date(2025, 11, 12), heures_en_moins=20, motif="PANNE")
        self.charges_courantes(450000, 55000)
        self.imputer("Réparation pompe de l'ultrafiltration", 300000, equipement=self.pompe_uf)
        Utilisateur.objects.create_user("cg", password="x", profil=Profil.CONTROLE_GESTION)
        cloture = cloturer(self.usine, MOIS)
        self.assertEqual(cloture.decision, "MAINTENU")
        self.assertFalse(CoutStandardEau.objects.filter(origine="REVISION").exists())
        # Les rejets au-delà du taux toléré sont signalés au contrôle de gestion.
        self.assertTrue(Notification.objects.filter(titre__startswith="Pertes anormales").exists())

    def test_mois_3_nouveau_standard_propose_puis_valide(self):
        self.mois_3()
        Utilisateur.objects.create_user("cg", password="x", profil=Profil.CONTROLE_GESTION)
        cloture = cloturer(self.usine, MOIS)
        self.assertEqual((cloture.decision, cloture.ecart_courant_pct), ("NOUVEAU_PROPOSE", Decimal("-8.2410")))
        propose = cloture.standard_propose
        self.assertEqual((propose.mois_application, propose.origine, propose.statut, propose.cout_m3),
                         ("2025-12", "REVISION", "PROPOSE", Decimal("3775.8821")))
        self.assertTrue(Notification.objects.filter(titre__startswith="Écart de coût de l'eau").exists())
        # Le mois suivant n'est pas clôturé : le contrôle de gestion peut valider le standard révisé.
        controle = self.client_pour(Profil.CONTROLE_GESTION)
        reponse = controle.post(f"/api/eau/couts-standards/{propose.pk}/valider/", {}, format="json")
        self.assertEqual(reponse.status_code, 200, reponse.data)
        self.assertEqual(CoutStandardEau.en_vigueur("2025-12", usine=self.usine).cout_m3, Decimal("3775.8821"))
        self.assertEqual(CoutStandardEau.en_vigueur(MOIS, usine=self.usine).cout_m3, Decimal("4115.0000"))
        reponse = controle.get(f"/api/eau/reel/evolution/?usine={self.usine.pk}")
        self.assertEqual(reponse.data["mois"], [{
            "mois": MOIS, "volume_m3": "200", "cout_m3": "7525.88", "cout_m3_courant": "3775.88", "cout_standard_m3": "4115.00",
            "ecart_total_pct": "82.89", "ecart_courant_pct": "-8.24", "decision": "NOUVEAU_PROPOSE",
            "decision_libelle": "Nouveau standard proposé (à valider)",
            "standard_propose": {"id": propose.pk, "mois_application": "2025-12", "cout_m3": "3775.88", "statut": "VALIDE"},
        }])

    def test_volume_trop_faible_standard_maintenu(self):
        """Moins de 50 % du volume prévu : le mois n'est pas représentatif, même avec un gros écart."""
        self.capter(220, 330)
        self.produire(30000, 20000, 2000, 0)          # 65 m³ pour 200 prévus
        self.charges_courantes(500000, 60000, entretien=120000)
        cloture = cloturer(self.usine, MOIS)
        self.assertEqual(cloture.decision, "MAINTENU_VOLUME_FAIBLE")
        self.assertIsNone(cloture.standard_propose)
        self.assertGreater(abs(cloture.ecart_courant_pct), 5)

    def test_un_standard_ne_change_pas_pour_un_mois_cloture(self):
        self.mois_1()
        cloturer(self.usine, MOIS)
        standard = CoutStandardEau.objects.create(usine=self.usine, mois_application=MOIS, origine="REVISION", volume_m3=1,
                                                  cout_forage=0, cout_traitement=0, cout_mensuel=1, cout_m3=1)
        with self.assertRaises(ValueError):
            standard.valider(None)
        self.assertEqual(len(evolution(self.usine)["mois"]), 1)


# =====================================================================
# Phase 7 - sorties de stock valorisées en PEPS / FIFO
# =====================================================================

from apps.stocks.models import MouvementStock, depot_par_defaut  # noqa: E402


class PepsTests(BaseScenario):

    def setUp(self):
        super().setUp()
        self.sel = Article.objects.create(code="SEL-REG", designation="Sel de régénération", type_article="MATIERE_PREMIERE", unite_mesure="KG")
        self.magasin = depot_par_defaut("Magasin principal")

    def mouvement(self, type_mouvement, quantite, le, cout=None, element=None):
        mouvement = MouvementStock.objects.create(
            article=self.sel, depot=self.magasin, type_mouvement=type_mouvement, quantite=quantite, cout_unitaire=cout,
            utilisateur=self.responsable, element_eau=element,
        )
        MouvementStock.objects.filter(pk=mouvement.pk).update(date_mouvement=timezone.make_aware(timezone.datetime(*le, 9)))
        return mouvement

    def stock_de_sel(self):
        """Deux achats (100 kg à 280, puis 200 kg à 320) et 200 kg sortis vers le traitement en novembre."""
        self.mouvement("ENTREE", 100, (2025, 10, 1), cout=280)
        self.mouvement("ENTREE", 200, (2025, 10, 20), cout=320)
        return self.mouvement("SORTIE", 200, (2025, 11, 10), element=self.elements["Sel de régénération"])

    def mois_1_avec_le_sel_en_stock(self):
        self.capter(220, 330)
        self.produire(100000, 60000, 4000, 1000)
        self.imputer("Électricité pompe du forage", 500000)
        self.imputer("Entretien préventif pompe du forage", 120000, equipement=self.pompe_forage)
        for libelle, montant in (("Produit de lavage des filtres", 20000), ("Analyses par laboratoire externe", 100000),
                                 ("Kits de contrôle interne", 43000)):
            self.imputer(libelle, montant)
        return self.stock_de_sel()

    def test_sortie_valorisee_en_peps_le_scenario_reste_juste(self):
        """200 kg = 100 x 280 + 100 x 320 = 60 000 (au CMUP du stock : 200 x 306,6667 = 61 333,34)."""
        sortie = self.mois_1_avec_le_sel_en_stock()
        self.assertEqual(sortie.valeur, Decimal("61333.34"))                 # la valeur comptable reste au CMUP
        calcul = calcul_reel(self.usine, MOIS)
        self.assertEqual(calcul["sorties_stock"]["valorisation"], "PEPS")
        self.assertEqual(calcul["sorties_stock"]["mouvements"][0]["valeur"], "60000.00")
        self.assertEqual(calcul["synthese"]["cout_reel_total"], "788467.27")
        statuts = {l["libelle"]: l["statut"] for l in calcul["charges_attendues"]}
        self.assertEqual(statuts["Sel de régénération"], "IMPUTEE")
        self.assertEqual(calcul["bloquants"], [])

    def test_methode_cmup_si_l_expert_comptable_la_retient(self):
        self.mois_1_avec_le_sel_en_stock()
        ParametresEau.objects.filter(usine=self.usine).update(valorisation_sorties_stock="CMUP")
        calcul = calcul_reel(self.usine, MOIS)
        self.assertEqual(calcul["sorties_stock"]["mouvements"][0]["valeur"], "61333.34")
        self.assertEqual(calcul["synthese"]["cout_reel_total"], "789800.61")   # + 1 333,34 au traitement

    def test_un_retour_au_magasin_diminue_la_consommation(self):
        self.mois_1_avec_le_sel_en_stock()
        self.mouvement("RETOUR", 20, (2025, 11, 20), cout=300, element=self.elements["Sel de régénération"])
        self.assertEqual(calcul_reel(self.usine, MOIS)["synthese"]["cout_traitement"], "585705.94")   # - 20 x 300

    def test_les_sorties_suivantes_consomment_les_couches_suivantes(self):
        self.stock_de_sel()
        decembre = self.mouvement("SORTIE", 50, (2025, 12, 3), element=self.elements["Sel de régénération"])
        from apps.eau.peps import valeurs_peps
        self.assertEqual(valeurs_peps(self.sel)[decembre.pk], (Decimal(16000), Decimal(0)))   # 50 x 320

    def test_regles_des_sorties_vers_l_eau(self):
        with self.assertRaises(ValidationError):   # une pièce étalée s'installe, elle ne s'impute pas au mois
            self.mouvement("ENTREE", 10, (2025, 10, 1), cout=1, element=self.elements["Sel de régénération"])
        self.mouvement("ENTREE", 10, (2025, 10, 1), cout=1)
        with self.assertRaises(ValidationError):
            self.mouvement("SORTIE", 1, (2025, 11, 1), element=self.elements["Charbon actif"])
        with self.assertRaises(ValidationError):
            self.mouvement("SORTIE", 1, (2025, 11, 1), element=self.elements["Électricité pompe du forage"])
