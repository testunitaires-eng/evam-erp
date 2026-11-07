# EVAM Backend — Logiciel intégré de gestion (Groupe 2I)

Backend Django + Django REST Framework du logiciel décrit dans le
cahier des charges EVAM (production d'eau, de jus et de yaourt). Il
expose uniquement une API REST : l'interface utilisateur est un projet
séparé (front autorisé par CORS sur `http://localhost:3000` en
développement).

Ce README est écrit pour quelqu'un qui n'a pas suivi la construction
du projet et doit pouvoir l'installer, le comprendre et le faire
évoluer seul.

---

## 1. Ce que contient ce dépôt

```
evam-erp/
├── manage.py                  <- point d'entrée des commandes Django
├── requirements.txt           <- dépendances Python (versions figées)
├── .env.example               <- variables d'environnement à copier en .env
├── config/                    <- réglages globaux du projet
│   ├── settings.py
│   └── urls.py                <- toutes les routes /api/... du projet
└── apps/                      <- une application Django par module métier
    ├── core/                  <- transverse : numérotation, historique, notifications,
    │                             PDF, exports, paramètres de l'entreprise, pagination
    ├── comptes/               <- utilisateurs, 12 profils, permissions, journal des actions
    ├── industriel/            <- socle : activités, usines, lignes, postes, équipements, circuits
    ├── referentiel/           <- articles, familles, formats, fiches techniques, conversions d'unités
    ├── fiscalite/             <- matrice fiscale par produit, préparation de la facture normalisée (SFEC)
    ├── achats/                <- fournisseurs, besoins, demandes, commandes, réceptions, retours
    ├── stocks/                <- dépôts, stock par dépôt, mouvements, inventaires, transferts,
    │                             lots matières, emplacements, palettes, valorisation
    ├── production/            <- plans, ordres de fabrication (OF), besoins, demandes et sorties
    │                             de matières, réservations, suivi de l'eau, étapes, pertes
    ├── qualite/               <- lots, contrôles, plan de contrôle, instruments, non-conformités
    ├── commercial/            <- clients, prospects, contrats, tarifs, devis, commandes, factures, avoirs
    ├── caisse/                <- caisses, sessions, encaissements, écarts, décaissements
    ├── distribution/          <- véhicules, chauffeurs, tournées, préparations, bons de livraison
    ├── reclamations/          <- retours clients : réclamation, retour physique, contrôle, solution
    ├── couts/                 <- coûts réels et standards, charges, clés de répartition
    ├── comptabilite/          <- écritures automatiques, plan de comptes, anomalies, exports, clôtures
    ├── personnel/             <- ouvriers (sans accès à l'application), compétences, affectations
    └── reporting/             <- tableau de bord de la Direction
```

Chaque application suit la même organisation :

| Fichier | Rôle |
|---|---|
| `models.py` | Les tables et **les règles métier** (validation avant chaque enregistrement, transitions de statut, effets automatiques), commentées en français avec la référence au cahier des charges |
| `serializers.py` | La conversion des modèles en JSON pour l'API |
| `views.py` | Les endpoints et **les permissions par profil** |
| `urls.py` | Les routes de l'application (ex : `/api/production/ordres-fabrication/`) |
| `admin.py` | L'interface d'administration Django (`/admin/`) |
| `tests*.py` | Les tests automatisés |

---

## 2. Installation (pas à pas)

### Prérequis
- Python 3.12 ou supérieur (exigé par Django 6.1)
- pip

### Étapes

```bash
# 1. Se placer dans le dossier du projet
cd evam-erp

# 2. Créer et activer un environnement virtuel
python3 -m venv venv
source venv/bin/activate          # sous Windows : venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Copier le fichier de configuration
cp .env.example .env
# (ouvrir .env et changer DJANGO_SECRET_KEY avant toute mise en production)

# 5. Créer la base de données (SQLite par défaut en local)
python manage.py migrate

# 6. (recommandé) Charger les valeurs de départ
python manage.py initialiser_matrice_fiscale        # codes fiscaux
python manage.py initialiser_referentiel_valeurs    # familles, formats, parfums...

# 7. Créer un compte administrateur
python manage.py createsuperuser

# 8. (optionnel) Créer un compte de démonstration par profil métier
#    (12 comptes, identifiant = nom du profil en minuscules,
#    mot de passe "Demo1234!" pour tous)
python manage.py creer_comptes_demo

# 9. Lancer le serveur de développement
python manage.py runserver
```

L'application est alors accessible sur :
- **API** : http://127.0.0.1:8000/api/
- **Documentation interactive (Swagger)** : http://127.0.0.1:8000/api/docs/
- **Interface d'administration** : http://127.0.0.1:8000/admin/

### Base de données

- **En local** : SQLite (`db.sqlite3`), rien à installer.
- **En production** : PostgreSQL, configuré par la variable
  d'environnement `DATABASE_URL`
  (ex : `postgres://utilisateur:motdepasse@hote:5432/nom_base`).
  C'est le cas du déploiement Railway actuel.

Chaque requête HTTP s'exécute dans une transaction (`ATOMIC_REQUESTS`) :
si une erreur survient au milieu d'un traitement, rien n'est enregistré.

---

## 3. Se connecter à l'API (authentification)

L'API utilise des jetons JWT (JSON Web Token). Chaque requête doit
porter un jeton dans son en-tête.

**Étape 1 — obtenir un jeton :**
```bash
curl -X POST http://127.0.0.1:8000/api/auth/connexion/ \
  -H "Content-Type: application/json" \
  -d '{"username": "responsable_production", "password": "Demo1234!"}'
```
Réponse :
```json
{"refresh": "eyJhbGci...", "access": "eyJhbGci..."}
```

**Étape 2 — utiliser le jeton `access` dans chaque requête :**
```bash
curl http://127.0.0.1:8000/api/production/ordres-fabrication/ \
  -H "Authorization: Bearer eyJhbGci..."
```

Le jeton `access` expire au bout de 8 heures ; utiliser le jeton
`refresh` sur `/api/auth/rafraichir/` pour en obtenir un nouveau sans
se reconnecter. Chaque connexion est enregistrée dans le journal des
actions.

Les listes sont paginées par 25 (`?page=2`). Une liste sans ordre
explicite est triée de la plus récente à la plus ancienne ; le tri se
change avec `?ordering=<champ>`.

---

## 4. Les 12 profils et leurs droits

Chaque utilisateur a **un seul profil** (`Utilisateur.profil`). Le
cahier des charges décrit 11 acteurs ; un 12e (**Responsable Achat**)
a été ajouté car le module Achats est détaillé sans que le document ne
nomme qui le pilote — point confirmé avec le client.

| Profil (identifiant technique) | Peut créer/modifier | Lecture seule sur / Restrictions |
|---|---|---|
| `RESPONSABLE_PRODUCTION` | Fiches techniques, plans de production, OF, validation des sorties complémentaires, ouvriers et leurs affectations | Coûts (jamais accès aux prix) |
| `AGENT_PRODUCTION` | Étapes de production, pertes | **Ne voit que les OF où il figure dans `agents_affectes`** ; consulte les ouvriers et affectations |
| `MAGASINIER` | Mouvements de stock, sorties matières, préparations de livraison, réceptions, retours fournisseurs | Fiches techniques (refusé en écriture), OF |
| `RESPONSABLE_QUALITE` | Contrôles qualité, libération/blocage des lots | — |
| `RESPONSABLE_ACHATS` | Fournisseurs, contrats, catalogue produits/prix, demandes d'achat (approbation), commandes fournisseurs | Réceptions et retours (partagés avec le Magasinier) |
| `COMMERCIAL` | Clients, prospects, contrats, tarifs, devis, commandes, factures | Stock disponible (jamais de modification) |
| `CAISSIER` | Sessions de caisse, encaissements, justification d'écarts | Commandes, prix (aucune modification), **ne peut jamais supprimer un écart** |
| `RESPONSABLE_DISTRIBUTION` | Tournées, lancement des préparations, confirmation des livraisons | — |
| `CHAUFFEUR` | Confirmation de livraison | **Ne voit que ses propres tournées et bons de livraison** |
| `COMPTABILITE_DAF` | Anomalies, exports comptables, clôtures, plan de comptes | Lecture transversale sur la plupart des modules |
| `DIRECTION` | — | Tableaux de bord, coûts, journal des actions |
| `ADMIN_SI` | Utilisateurs et tous les modules | — (accès total) |

### Où sont codées les permissions

Dans chaque `views.py`, via `apps/comptes/permissions.py` :

```python
permission_classes = [acces(
    lecture=(Profil.DIRECTION, Profil.COMPTABILITE_DAF),          # consultent seulement
    ecriture=(Profil.RESPONSABLE_ACHATS, Profil.ADMIN_SI),        # consultent et modifient
)]
```

Tout profil absent des deux listes n'a **aucun accès**, même en
lecture. Un superutilisateur passe toujours ; un compte désactivé est
toujours refusé. Quelques vues utilisent encore `role_required(...)`
(accès complet pour les profils listés). Pour changer qui a accès à
quoi, c'est le seul endroit à modifier.

Les restrictions plus fines (un agent ne voit que ses OF, un chauffeur
ses tournées, seul le Responsable Achat approuve une demande...) sont
dans les `get_queryset()` et les actions des vues concernées.

---

## 5. Workflows métier importants

Au-delà du CRUD standard, des **actions** appliquent les règles de
workflow. Les statuts ne peuvent pas être modifiés directement : ils
avancent uniquement par ces actions ou par les effets automatiques
décrits plus bas.

| Action | Endpoint | Effet |
|---|---|---|
| Valider une fiche technique | `POST /api/referentiel/fiches-techniques/{id}/valider/` | Brouillon → Validée |
| Avancer un OF | `POST /api/production/ordres-fabrication/{id}/avancer_statut/` | Une étape du workflow (Brouillon → … → Clôturé). Au lancement : contrôle du stock et **réservation des matières** ; à la clôture : contrôles qualité bloquants, libération du reste réservé |
| Annuler un OF | `POST /api/production/ordres-fabrication/{id}/annuler/` | Motif obligatoire, réservations libérées |
| Libérer / bloquer un lot | `POST /api/qualite/lots/{id}/liberer/` · `.../bloquer/` | **Seul un lot libéré est vendable** |
| Approuver / rejeter une demande d'achat | `POST /api/achats/demandes/{id}/approuver/` · `.../rejeter/` | Responsable Achat (ou Administrateur SI) |
| Créer une demande depuis un besoin | `POST /api/achats/besoins/{id}/creer_demande/` | Reprend l'article et la quantité du besoin |
| Envoyer une commande fournisseur | `POST /api/achats/commandes/{id}/envoyer/` | Brouillon → Envoyée (refusé sans lignes) |
| Confirmer la préparation / la sortie | `POST /api/distribution/preparations/{id}/confirmer_preparation/` · `.../confirmer_sortie/` | Sortie de stock tout-ou-rien |
| Confirmer une livraison | `POST /api/distribution/bons-livraison/{id}/confirmer_livraison/` | Bon de livraison Livré |
| Clôturer une session de caisse | `POST /api/caisse/sessions/{id}/cloturer/` | Calcule l'écart ; un écart doit être justifié |

Les documents à imprimer sont disponibles en PDF sur `.../{id}/pdf/`
(bon de commande fournisseur, bon de livraison, facture...), et
l'historique des changements de statut sur `.../{id}/historique/`.

### Effets automatiques (sans action de l'utilisateur)

- **Besoins matières d'un OF** : calculés dès la création de l'OF à
  partir de la fiche technique validée, recalculés si la quantité ou
  l'article change tant que l'OF est en brouillon.
- **Réception fournisseur** (ligne de réception) : met à jour la
  commande (partiellement reçue / reçue), crée l'entrée en stock (avec
  conversion d'unité d'achat → unité de stock), le lot matière
  (bloqué si la réception est non conforme, « à contrôler » si le plan
  qualité l'exige) et l'écriture comptable d'achat.
- **Retour fournisseur** : sortie de stock, retrait des lots concernés
  et écriture comptable inverse.
- **Besoins d'achat** : un seul besoin automatique ouvert par matière
  achetée, recalculé à chaque mouvement de stock et à chaque changement
  d'OF, de demande ou de commande :
  `besoins des OF non terminés + seuil d'alerte − stock disponible −
  achats en cours − besoins saisis à la main`. Il est rattaché aux OF
  concernés et le Responsable Achat est notifié à sa création.
- **Écritures comptables** : facture, encaissement, décaissement, avoir,
  réception et retour fournisseur, synthèse de caisse (voir
  `apps/comptabilite/ecritures.py`). Une écriture déséquilibrée ou sur
  une période clôturée annule toute l'opération.
- **Notifications** : envoyées aux profils concernés à chaque étape
  clé (demande d'achat à approuver, réception attendue, commande à
  servir...) — `GET /api/notifications/`.

### Ouvriers (module `personnel`)

Les ouvriers travaillent aux étapes de production mais **n'ont jamais
de compte** : ce sont de simples fiches (`/api/personnel/ouvriers/`),
distinctes des utilisateurs.

- **Permanent** ou **temporaire** : un temporaire a obligatoirement une
  date de fin de contrat. Matricule automatique (`OUV-000001`).
- **Zones de compétence** : les étapes du processus (`EtapeStandard`)
  que l'ouvrier sait tenir. On ajoute une zone hors ligne (nettoyage,
  magasin...) en créant l'étape correspondante dans le socle industriel.
- **Affectations** (`/api/personnel/affectations/`) : à une étape ou un
  poste précis pour une période, ou à l'équipe d'un OF (période reprise
  du planning de l'OF). Contrôles : ouvrier actif, sous contrat sur
  toute la période (un temporaire est limité à sa fin de contrat),
  compétent pour l'étape, jamais sur deux postes en même temps ; un
  même ouvrier peut en revanche travailler sur plusieurs OF.
- **Ouvriers disponibles** pour une étape à une date :
  `GET /api/personnel/ouvriers/disponibles/?etape=<id>&date=AAAA-MM-JJ`.
- **Départ** : désactiver la fiche avec un motif ; les affectations en
  cours s'arrêtent le jour même, celles à venir sont retirées. Une fiche
  déjà affectée ne se supprime pas.

Prévu ensuite : rémunération (mensuelle, hebdomadaire, journalière...),
pointages, états de paie, écritures comptables et coût de main-d'œuvre
par OF.

---

## 6. Numérotation automatique

Conformément au cahier des charges (§16.1), tous les documents (OF,
lot, commande, facture, bon de livraison, écriture...) reçoivent un
numéro automatique du type `OF-000123`, généré par
`apps/core/models.py::generer_numero()`. Ce numéro n'est jamais
modifiable depuis l'API et jamais réutilisé. Les codes des fiches
(fournisseurs, articles...) sont aussi générés automatiquement.

---

## 7. Tests

```bash
python manage.py test               # toute la suite
python manage.py test --parallel 4  # plus rapide
python manage.py test apps.achats   # un seul module
```

La suite couvre les circuits entre modules (achats → stock → qualité →
comptabilité, commande → préparation → livraison → facture → caisse,
OF → réservations → sorties...), les permissions par profil et les
documents PDF. La plupart des tests sont dans `apps/core/tests.py` et
`apps/industriel/tests*.py`. Lancer la suite avant chaque mise en
production.

---

## 8. Ce qui reste à faire

**À finaliser avec le client :**
1. **Clé de répartition énergie/amortissement** dans le calcul du coût
   réel (`apps/couts`) : actuellement au prorata des quantités
   produites sur la période ; à confirmer avec le DAF.
2. **Intégration Sage 100** : les exports comptables
   (`/api/comptabilite/exports/{id}/telecharger/`) produisent un
   fichier CSV au format d'import Sage, ou un format générique
   CSV / Excel / JSON. À trancher : fichier suffisant, ou vraie
   interface API avec Sage ?
3. **Contrôles d'anomalies** : 10 types sont détectés
   (`python manage.py detecter_anomalies`, plus des contrôles au fil de
   l'eau) ; le cahier des charges (§14.3) en prévoit 14.
4. **Facture normalisée (SFEC)** : les données et l'architecture sont
   prêtes (`apps/fiscalite/sfec.py`), le connecteur réel reste à brancher
   quand l'administration fiscale ouvrira l'accès.

**Technique :**
- Configurer l'interface d'administration (colonnes, filtres,
  recherche) : la plupart des modèles y sont enregistrés sans réglage.
- Écrire des tests propres aux modules qui n'en ont pas encore.

---

## 9. Commandes utiles

```bash
python manage.py makemigrations          # après une modification de models.py
python manage.py migrate                 # appliquer les migrations
python manage.py check                   # vérifier la configuration
python manage.py shell                   # console Python avec Django chargé

python manage.py creer_comptes_demo               # comptes de démonstration (un par profil)
python manage.py initialiser_matrice_fiscale      # codes fiscaux de départ
python manage.py initialiser_referentiel_valeurs  # valeurs de référence de départ
python manage.py detecter_anomalies               # contrôles d'anomalies périodiques
```
