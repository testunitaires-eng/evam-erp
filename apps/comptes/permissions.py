"""
Permissions basées sur la matrice de droits configurable (MatriceDroit).

Remplace l'ancien système où chaque vue déclarait en dur la liste des
profils autorisés (role_required / lecture_seule_pour). Désormais,
c'est la table MatriceDroit qui décide, et l'Administrateur SI peut la
modifier depuis l'admin ou l'API SANS toucher au code ni redéployer.

Comment ça marche :
1. Chaque ViewSet précise sur quel Module il porte (ex: Module.ACHATS).
2. À chaque requête, on regarde l'action DRF en cours (list, create,
   update, destroy, ou une action personnalisée comme "valider").
3. On traduit cette action en un champ booléen de MatriceDroit
   (peut_consulter, peut_creer, peut_modifier, peut_valider,
   peut_annuler, peut_exporter, peut_parametrer) via ACTIONS_PAR_DEFAUT,
   éventuellement surchargé par le ViewSet.
4. On va chercher la ligne (profil de l'utilisateur, module) dans
   MatriceDroit et on regarde si ce champ est à True.

Si aucune ligne n'existe pour ce (profil, module), l'accès est REFUSÉ
par défaut (sécurité par défaut : on n'autorise que ce qui est
explicitement coché). C'est pourquoi la commande de gestion
`initialiser_matrice_droits` doit être lancée après la migration, sinon
plus personne (sauf l'Administrateur SI) ne peut rien faire.
"""

from rest_framework.permissions import BasePermission

# Correspondance par défaut entre l'action DRF et le champ de
# MatriceDroit à vérifier pour les actions CRUD standard.
ACTIONS_PAR_DEFAUT = {
    "list": "peut_consulter",
    "retrieve": "peut_consulter",
    "create": "peut_creer",
    "update": "peut_modifier",
    "partial_update": "peut_modifier",
    "destroy": "peut_annuler",
}

# Toute action personnalisée (@action, ex: "valider", "liberer",
# "avancer_statut"...) qui n'est pas listée explicitement dans
# actions_supplementaires est traitée par défaut comme une action de
# workflow/validation.
CHAMP_ACTION_PERSONNALISEE_PAR_DEFAUT = "peut_valider"


def a_le_droit(utilisateur, module, champ):
    """
    Fonction utilitaire réutilisable partout (permission_classes ET
    vérifications manuelles à l'intérieur d'une vue) : est-ce que ce
    profil a CE droit sur CE module, d'après la matrice de droits ?

    Toujours True pour un superutilisateur. Toujours False pour un
    compte désactivé (is_active=False), même si sa matrice l'autorise.
    """
    from .models import MatriceDroit  # import tardif : évite un import circulaire

    if not utilisateur or not utilisateur.is_authenticated:
        return False
    if not utilisateur.is_active:
        return False
    if utilisateur.is_superuser:
        return True

    droit = MatriceDroit.objects.filter(profil=utilisateur.profil, module=module).first()
    if droit is None:
        return False
    return getattr(droit, champ, False)


def droit_matrice(module, actions_supplementaires=None):
    """
    Retourne une classe de permission DRF branchée sur MatriceDroit
    pour le module donné.

    `actions_supplementaires` : dict optionnel {nom_action: champ}
    pour surcharger le mapping par défaut sur une vue précise.
    Exemple : un ViewSet d'export où l'action "create" doit vérifier
    "peut_exporter" plutôt que "peut_creer" :

        permission_classes = [droit_matrice(
            Module.COMPTABILITE, actions_supplementaires={"create": "peut_exporter"}
        )]
    """
    mapping = {**ACTIONS_PAR_DEFAUT, **(actions_supplementaires or {})}

    class DroitMatricePermission(BasePermission):
        message = ("Votre profil ne dispose pas de ce droit pour ce module "
                   "(voir la matrice de droits, module Administration).")

        def has_permission(self, request, view):
            utilisateur = request.user
            if not utilisateur or not utilisateur.is_authenticated:
                return False
            if not utilisateur.is_active:
                return False
            if utilisateur.is_superuser:
                return True

            action = getattr(view, "action", None)
            champ = mapping.get(action, CHAMP_ACTION_PERSONNALISEE_PAR_DEFAUT)
            return a_le_droit(utilisateur, module, champ)

    return DroitMatricePermission
