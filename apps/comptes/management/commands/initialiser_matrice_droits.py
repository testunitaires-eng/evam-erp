"""
Remplit la matrice de droits (MatriceDroit) avec des valeurs de départ
cohérentes, reprenant les règles qui étaient auparavant codées en dur
dans chaque views.py.

À lancer UNE FOIS après la migration qui introduit la matrice de
droits :

    python manage.py initialiser_matrice_droits

Sans cette étape, la table est vide et personne (sauf superutilisateur)
n'a plus aucun droit nulle part, puisque le nouveau système refuse par
défaut ce qui n'est pas explicitement autorisé.

Cette commande ne fait qu'ajouter les lignes manquantes (elle ne
touche jamais une ligne déjà modifiée par l'Administrateur SI) :
relancer la commande plus tard pour ajouter un nouveau module ou
profil est donc sans danger.
"""

from django.core.management.base import BaseCommand
from apps.comptes.models import MatriceDroit, Profil, Module


# Chaque tuple : (profil, module, {champs à True})
# Tout champ non mentionné reste à False (valeur par défaut du modèle).
DROITS_PAR_DEFAUT = [
    # --- Responsable Production ---
    (Profil.RESPONSABLE_PRODUCTION, Module.REFERENTIEL, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True)),
    (Profil.RESPONSABLE_PRODUCTION, Module.PRODUCTION, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True, peut_annuler=True)),
    (Profil.RESPONSABLE_PRODUCTION, Module.STOCKS, dict(peut_consulter=True)),
    (Profil.RESPONSABLE_PRODUCTION, Module.QUALITE, dict(peut_consulter=True)),
    (Profil.RESPONSABLE_PRODUCTION, Module.ACHATS, dict(peut_consulter=True, peut_creer=True)),  # peut créer une demande d'achat
    (Profil.RESPONSABLE_PRODUCTION, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Agent Production (accès restreint à ses OF affectés, filtré en plus par get_queryset) ---
    (Profil.AGENT_PRODUCTION, Module.PRODUCTION, dict(peut_consulter=True, peut_creer=True, peut_modifier=True)),
    (Profil.AGENT_PRODUCTION, Module.REFERENTIEL, dict(peut_consulter=True)),
    (Profil.AGENT_PRODUCTION, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Magasinier ---
    (Profil.MAGASINIER, Module.STOCKS, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True)),  # inclut les transferts entre dépôts
    (Profil.MAGASINIER, Module.PRODUCTION, dict(peut_consulter=True, peut_creer=True)),  # sorties/retours matières
    (Profil.MAGASINIER, Module.REFERENTIEL, dict(peut_consulter=True)),  # jamais peut_creer/peut_modifier : ne touche pas aux fiches techniques
    (Profil.MAGASINIER, Module.ACHATS, dict(peut_consulter=True, peut_valider=True)),  # peut_valider réutilisé UNIQUEMENT pour réceptions/retours (voir ReceptionAchatViewSet) - jamais peut_creer/peut_modifier ici, pour ne pas pouvoir créer/gérer fournisseurs, contrats ou commandes
    (Profil.MAGASINIER, Module.DISTRIBUTION, dict(peut_consulter=True, peut_modifier=True)),  # confirmer préparation/sortie (PAS peut_creer : ne lance pas la préparation lui-même)
    (Profil.MAGASINIER, Module.QUALITE, dict(peut_consulter=True)),  # doit savoir quels lots sont vendables/sortables
    (Profil.MAGASINIER, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Responsable Qualité ---
    (Profil.RESPONSABLE_QUALITE, Module.QUALITE, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True)),
    (Profil.RESPONSABLE_QUALITE, Module.PRODUCTION, dict(peut_consulter=True)),
    (Profil.RESPONSABLE_QUALITE, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Responsable Achat ---
    (Profil.RESPONSABLE_ACHATS, Module.ACHATS, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True, peut_annuler=True)),
    (Profil.RESPONSABLE_ACHATS, Module.STOCKS, dict(peut_consulter=True)),
    (Profil.RESPONSABLE_ACHATS, Module.REFERENTIEL, dict(peut_consulter=True)),
    (Profil.RESPONSABLE_ACHATS, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Commercial ---
    (Profil.COMMERCIAL, Module.COMMERCIAL, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True, peut_annuler=True)),
    (Profil.COMMERCIAL, Module.STOCKS, dict(peut_consulter=True)),  # jamais peut_modifier : consultation seule
    (Profil.COMMERCIAL, Module.QUALITE, dict(peut_consulter=True)),  # doit savoir quels lots sont vendables
    (Profil.COMMERCIAL, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Caissier ---
    (Profil.CAISSIER, Module.CAISSE, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True)),
    (Profil.CAISSIER, Module.COMMERCIAL, dict(peut_consulter=True, peut_creer=True)),  # factures
    (Profil.CAISSIER, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Responsable Distribution ---
    (Profil.RESPONSABLE_DISTRIBUTION, Module.DISTRIBUTION, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True, peut_annuler=True)),
    (Profil.RESPONSABLE_DISTRIBUTION, Module.COMMERCIAL, dict(peut_consulter=True, peut_modifier=True)),
    (Profil.RESPONSABLE_DISTRIBUTION, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Chauffeur (accès restreint à ses tournées, filtré en plus par get_queryset) ---
    (Profil.CHAUFFEUR, Module.DISTRIBUTION, dict(peut_consulter=True, peut_modifier=True)),  # peut ajouter preuve/notes de livraison, mais pas confirmer_livraison (réservé à peut_valider)
    (Profil.CHAUFFEUR, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Comptabilité / DAF : accès transversal large, surtout en lecture ---
    (Profil.COMPTABILITE_DAF, Module.COMPTABILITE, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True, peut_exporter=True)),
    (Profil.COMPTABILITE_DAF, Module.COUTS, dict(peut_consulter=True, peut_creer=True, peut_modifier=True, peut_valider=True)),
    (Profil.COMPTABILITE_DAF, Module.ACHATS, dict(peut_consulter=True)),
    (Profil.COMPTABILITE_DAF, Module.COMMERCIAL, dict(peut_consulter=True, peut_modifier=True)),  # factures
    (Profil.COMPTABILITE_DAF, Module.CAISSE, dict(peut_consulter=True, peut_modifier=True)),  # écarts
    (Profil.COMPTABILITE_DAF, Module.STOCKS, dict(peut_consulter=True)),
    (Profil.COMPTABILITE_DAF, Module.PRODUCTION, dict(peut_consulter=True)),
    (Profil.COMPTABILITE_DAF, Module.ADMINISTRATION, dict(peut_consulter=True)),  # journal des actions
    (Profil.COMPTABILITE_DAF, Module.ACCUEIL, dict(peut_consulter=True)),

    # --- Direction : lecture seule, très large ---
    (Profil.DIRECTION, Module.ACCUEIL, dict(peut_consulter=True)),
    (Profil.DIRECTION, Module.COUTS, dict(peut_consulter=True)),
    (Profil.DIRECTION, Module.PRODUCTION, dict(peut_consulter=True)),
    (Profil.DIRECTION, Module.COMMERCIAL, dict(peut_consulter=True)),
    (Profil.DIRECTION, Module.STOCKS, dict(peut_consulter=True)),
    (Profil.DIRECTION, Module.ADMINISTRATION, dict(peut_consulter=True)),

    # --- Administrateur SI : accès total à tous les modules ---
    *[
        (Profil.ADMIN_SI, module, dict(
            peut_consulter=True, peut_creer=True, peut_modifier=True,
            peut_valider=True, peut_annuler=True, peut_exporter=True, peut_parametrer=True,
        ))
        for module in Module.values
    ],
]


class Command(BaseCommand):
    help = "Initialise la matrice de droits avec des valeurs de départ cohérentes (à lancer une fois après migration)."

    def handle(self, *args, **options):
        crees = 0
        ignores = 0
        for profil, module, champs in DROITS_PAR_DEFAUT:
            _, cree = MatriceDroit.objects.get_or_create(
                profil=profil, module=module, defaults=champs,
            )
            if cree:
                crees += 1
                self.stdout.write(self.style.SUCCESS(f"  + {profil} / {module}"))
            else:
                ignores += 1
        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé : {crees} lignes créées, {ignores} déjà existantes (non modifiées)."
        ))
