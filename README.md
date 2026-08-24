# EVAM Backend — Logiciel intégré de gestion (Groupe 2I)

Backend Django + Django REST Framework du logiciel décrit dans le
cahier des charges EVAM. Il couvre les 11 modules métier identifiés
dans le document (référentiel, achats, stocks, production, qualité,
commercial, caisse, distribution, coûts, comptabilité, administration
des droits).

Ce README est volontairement très détaillé : il est écrit pour
quelqu'un qui n'a pas suivi la construction du projet et doit pouvoir
l'installer, le comprendre et le faire évoluer seul.

---

## 1. Ce que contient ce dépôt

```
evam_backend/
├── manage.py                  <- point d'entrée des commandes Django
├── requirements.txt           <- dépendances Python
├── .env.example                <- variables d'environnement à copier en .env
├── config/                     <- réglages globaux du projet
│   ├── settings.py
│   └── urls.py                 <- toutes les routes /api/... du projet
└── apps/                       <- une application Django par module métier
    ├── core/                   <- utilitaires transverses (numérotation auto)
    ├── comptes/                <- Module 12 : utilisateurs, profils, droits
    ├── referentiel/            <- Module 2  : articles, fiches techniques
    ├── achats/                 <- Module 3  : fournisseurs, commandes fournisseurs
    ├── stocks/                 <- Module 4  : dépôts, mouvements, inventaires
    ├── production/             <- Module 5  : plan de production, OF, sorties matières
    ├── qualite/                <- Module 6  : lots, contrôle qualité, traçabilité
    ├── commercial/             <- Module 7  : clients, commandes, factures
    ├── caisse/                 <- Module 8  : sessions de caisse, encaissements
    ├── distribution/           <- Module 9  : préparation, tournées, livraisons
    ├── couts/                  <- Module 10 : coûts standards/réels, rentabilité
    └── comptabilite/           <- Module 11 : anomalies, exports, clôtures
```

Chaque application contient les mêmes 5 fichiers, avec les mêmes
règles à chaque fois :

| Fichier | Rôle |
|---|---|
| `models.py` | Les tables de la base de données, avec commentaires en français expliquant chaque règle métier tirée du cahier des charges |
| `serializers.py` | La conversion des modèles en JSON pour l'API |
| `views.py` | La logique des endpoints, **c'est ici que sont appliquées les permissions par profil** |
| `urls.py` | Les routes de l'application (ex : `/api/production/ordres-fabrication/`) |
| `admin.py` | L'interface d'administration Django (`/admin/`) |

---

## 2. Installation (pas à pas)

### Prérequis
- Python 3.11 ou supérieur
- pip

### Étapes

```bash
# 1. Se placer dans le dossier du projet
cd evam_backend

# 2. Créer et activer un environnement virtuel
python3 -m venv venv
source venv/bin/activate          # sous Windows : venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Copier le fichier de configuration
cp .env.example .env
# (ouvrir .env et changer DJANGO_SECRET_KEY avant toute mise en production)

# 5. Créer la base de données (SQLite par défaut, aucune installation
#    supplémentaire nécessaire pour démarrer)
python manage.py migrate

# 6. Créer un compte administrateur
python manage.py createsuperuser

# 7. (optionnel mais recommandé) Créer un compte de test pour chacun
#    des 11 profils métier, mot de passe "Demo1234!" pour tous
python manage.py creer_comptes_demo

# 8. Lancer le serveur de développement
python manage.py runserver
```

L'application est alors accessible sur :
- **API** : http://127.0.0.1:8000/api/
- **Documentation interactive (Swagger)** : http://127.0.0.1:8000/api/docs/
- **Interface d'administration** : http://127.0.0.1:8000/admin/

---

## 3. Se connecter à l'API (authentification)

L'API utilise des jetons JWT (JSON Web Token). Pas de session
classique : chaque requête doit porter un jeton dans son en-tête.

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
se reconnecter.

---

## 4. Les 12 profils et leurs droits

Chaque utilisateur a **un seul profil** (`Utilisateur.profil`), qui
détermine ce qu'il peut faire. Le cahier des charges décrit 11
acteurs ; un 12e (**Responsable Achat**) a été ajouté car le module
Achats (§6) y est détaillé sans que le document ne nomme jamais qui
le pilote — point confirmé avec le client. Voici la correspondance
avec les règles métier, telle qu'implémentée dans `views.py` de
chaque module :

| Profil (identifiant technique) | Peut créer/modifier | Lecture seule sur / Restrictions |
|---|---|---|
| `RESPONSABLE_PRODUCTION` | Fiches techniques, plans de production, OF, validation des sorties complémentaires | Coûts (jamais accès aux prix) |
| `AGENT_PRODUCTION` | Étapes de production, pertes | **Ne voit que les OF où il figure dans `agents_affectes`** (implémenté via `get_queryset()`) |
| `MAGASINIER` | Mouvements de stock, sorties matières, préparations de livraison, réceptions, retours fournisseurs | Fiches techniques (accès refusé en écriture), OF |
| `RESPONSABLE_QUALITE` | Contrôles qualité, libération/blocage des lots | — |
| `RESPONSABLE_ACHATS` | **Fournisseurs, contrats fournisseurs, catalogue produits/prix, demandes d'achat, commandes fournisseurs** | Réceptions et retours (partagés en écriture avec le Magasinier) |
| `COMMERCIAL` | Clients, prospects, contrats, tarifs, commandes, factures | Stock disponible (jamais de modification) |
| `CAISSIER` | Sessions de caisse, encaissements, justification d'écarts | Commandes, prix (aucune modification possible), **ne peut jamais supprimer un écart** |
| `RESPONSABLE_DISTRIBUTION` | Tournées, lance les préparations, confirme les livraisons | — |
| `CHAUFFEUR` | Confirmation de livraison | **Ne voit que ses propres tournées et bons de livraison** (`chauffeur__utilisateur=request.user`) |
| `COMPTABILITE_DAF` | Anomalies, exports comptables, clôtures | Accès transversal en LECTURE à presque tous les modules |
| `DIRECTION` | — | Tableaux de bord, coûts, journal des actions (lecture seule) |
| `ADMIN_SI` | Utilisateurs, matrice de droits, tous les modules | — (accès total) |

### Le module Achats en détail (Responsable Achat)

Le module (`apps/achats/`) couvre maintenant tous les onglets prévus
par le cahier des charges (§6.1) :

- **Fournisseurs** (`/api/achats/fournisseurs/`) : fiche fournisseur, géré par le Responsable Achat
- **Contrats fournisseurs** (`/api/achats/contrats-fournisseurs/`) : conditions, durée, statut - exclusivement Responsable Achat
- **Catalogue** (`/api/achats/catalogue-fournisseurs/`) : quel fournisseur livre quel article, à quel prix, sous quel délai - c'est la table `ArticleFournisseur`, qui répond directement à "achats des produits fournis par les fournisseurs"
- **Besoins d'approvisionnement** (`/api/achats/besoins/`) : générés automatiquement par la production ou saisis à la main
- **Demandes d'achat** (`/api/achats/demandes/`) : une demande interne (ex. du Responsable Production) que le Responsable Achat approuve (`POST .../approuver/`) ou rejette (`POST .../rejeter/`) avant de créer la commande
- **Commandes fournisseurs** (`/api/achats/commandes/`) : `POST .../envoyer/` fait passer de Brouillon à Envoyée
- **Réceptions et lignes de réception** (`/api/achats/receptions/`, `/api/achats/lignes-reception/`) : le Magasinier réceptionne physiquement ; chaque ligne de réception **met à jour automatiquement** la quantité reçue de la commande et son statut (Partiellement reçue / Reçue)
- **Retours fournisseurs** (`/api/achats/retours/`) : marchandise reçue puis retournée

Le mécanisme technique est dans `apps/comptes/permissions.py`
(fonctions `role_required()` et `lecture_seule_pour()`), utilisé dans
chaque `views.py`. Pour changer qui a accès à quoi, c'est **le seul
fichier à modifier par vue** — pas besoin de toucher aux modèles.

La table `MatriceDroit` (module `comptes`) existe en plus, comme
prévu par le cahier des charges, pour une configuration fine et
consultable depuis l'admin — mais elle n'est pas encore branchée
automatiquement aux permissions du code (voir section 7, Limites
connues).

---

## 5. Workflows métier importants (actions spéciales de l'API)

Au-delà du CRUD standard (créer/lire/modifier/supprimer), certains
endpoints exposent des **actions** qui appliquent les règles de
workflow du cahier des charges :

| Action | Endpoint | Qui peut l'appeler | Effet |
|---|---|---|---|
| Valider une fiche technique | `POST /api/referentiel/fiches-techniques/{id}/valider/` | Responsable Production | Passe la fiche de Brouillon à Validée |
| Avancer le statut d'un OF | `POST /api/production/ordres-fabrication/{id}/avancer_statut/` | Responsable Production | Fait progresser l'OF dans son workflow (Brouillon → ... → Clôturé). Au passage à "Lancé", **calcule automatiquement les besoins matières** à partir de la fiche technique |
| Libérer un lot | `POST /api/qualite/lots/{id}/liberer/` | Responsable Qualité | Passe le lot en Libéré (uniquement si Conforme) — **seul un lot Libéré est vendable** |
| Bloquer un lot | `POST /api/qualite/lots/{id}/bloquer/` | Responsable Qualité | Passe le lot en Bloqué |
| Confirmer la préparation | `POST /api/distribution/preparations/{id}/confirmer_preparation/` | Magasinier | Passe la préparation en "En préparation" |
| Confirmer la sortie magasin | `POST /api/distribution/preparations/{id}/confirmer_sortie/` | Magasinier | Passe la préparation en "Sortie magasin" |
| Confirmer une livraison | `POST /api/distribution/bons-livraison/{id}/confirmer_livraison/` | Responsable Distribution | Marque le bon de livraison comme Livré |
| Clôturer une session de caisse | `POST /api/caisse/sessions/{id}/cloturer/` | Caissier | Calcule l'écart entre solde théorique et solde compté ; si écart, avertit qu'une justification est obligatoire |

Toutes les autres opérations (lister, créer, consulter, modifier une
ligne) passent par les routes standards générées automatiquement par
Django REST Framework et visibles sur `/api/docs/`.

---

## 6. Numérotation automatique

Conformément au cahier des charges (§16.1 : "numérotation automatique
unique pour chaque pièce"), tous les documents (OF, lot, commande,
facture, bon de livraison, mouvement de stock, encaissement...)
reçoivent un numéro automatique du type `OF-000123`, généré par
`apps/core/models.py::generer_numero()`. Ce numéro n'est jamais
modifiable depuis l'API (`editable=False`) et jamais réutilisé.

---

## 7. Ce qui est fait, et ce qui reste à faire

**Fait et fonctionnel (testé de bout en bout) :**
- Les 12 modules métier (11 du cahier des charges + Responsable Achat), avec leurs modèles fidèles au document
- Le module Achats complet : fournisseurs, contrats, catalogue produits/prix, demandes d'achat, commandes, réceptions avec mise à jour automatique du statut, retours
- L'authentification par profil et les permissions par module/action
- **L'Agent Production ne voit que ses OF affectés** (`agents_affectes`), **le Chauffeur ne voit que ses propres tournées/livraisons** — restrictions testées et fonctionnelles
- Les workflows de statuts (OF, lot, préparation, livraison, session de caisse, commande fournisseur)
- **Le calcul réel des coûts** (`CoutReel.calculer()`, action `POST .../recalculer/`) : matières valorisées sur les sorties nettes, main-d'œuvre, énergie et amortissements répartis au prorata des quantités produites sur la période — formule fonctionnelle, clé de répartition à confirmer avec le DAF (voir point 1 ci-dessous)
- La numérotation automatique
- La traçabilité (modèle `JournalAction`, à appeler depuis les vues qui en ont besoin)
- La documentation API interactive (Swagger)
- Un jeu de comptes de démonstration (un par profil, y compris `responsable_achats`)

**À finaliser avec le client avant mise en production :**
1. **Clé de répartition énergie/amortissement** dans `CoutReel.calculer()` :
   la méthode actuelle répartit au prorata des quantités produites sur
   le mois. Si le client utilise une autre clé (heures machine, par
   exemple), la formule est à ajuster - elle est isolée dans une seule
   méthode bien commentée, donc facile à modifier.
2. **Intégration Sage 100** (`apps/comptabilite/models.py::ExportComptable`) :
   actuellement pensé comme un export fichier (CSV/Excel)
   téléchargeable. À trancher avec le client : export fichier
   suffisant, ou vraie interface API avec Sage ?
3. **Les 14 contrôles d'anomalies** du §14.3 : la liste `TypeAnomalie`
   dans `apps/comptabilite/models.py` est un point de départ à
   compléter avec les 14 contrôles exacts attendus, et la détection
   automatique elle-même (signaux Django déclenchés sur chaque
   module) reste à écrire.
4. **Transferts entre dépôts et double mouvement de stock** : le
   modèle `TransfertDepot` existe mais la logique de création
   automatique des deux mouvements (sortie + entrée) n'est pas encore
   implémentée.
5. **Matrice de droits dynamique** (`MatriceDroit`) : la table existe
   et est éditable depuis l'admin, mais les permissions réelles sont
   encore codées en dur par profil dans chaque `views.py` (plus
   simple à auditer). Brancher `MatriceDroit` dessus est possible mais
   pas fait, pour ne pas fragiliser des règles de sécurité qui doivent
   rester fiables.
6. **Tests automatisés** : aucun test unitaire n'est encore écrit
   (les vérifications de ce backend ont été faites manuellement via
   l'API). Recommandé avant mise en production, en particulier sur
   les workflows de statuts et les permissions par profil.
7. **Base de données de production** : SQLite convient pour le
   développement, mais une vraie mise en production doit utiliser
   PostgreSQL (changer `DATABASES` dans `config/settings.py`).

---

## 8. Commandes utiles

```bash
# Créer les fichiers de migration après une modification de models.py
python manage.py makemigrations

# Appliquer les migrations à la base de données
python manage.py migrate

# Ouvrir une console Python avec l'environnement Django chargé
python manage.py shell

# Recréer les 11 comptes de démonstration
python manage.py creer_comptes_demo

# Vérifier qu'il n'y a pas d'erreur de configuration
python manage.py check
```

---

## 9. Prochaine étape suggérée

Le fichier `EVAM_Backlog_Jira_FR.csv` (généré séparément) découpe ce
travail en tâches Jira avec estimation et échéances. Ce backend
correspond principalement aux tâches de la **Phase 1** (référentiel,
droits) et pose les fondations des **Phases 2 à 6** — la logique
technique métier fine (calculs de coûts, contrôles d'anomalies,
restrictions d'accès par affectation) reste à construire au fil des
phases suivantes.
