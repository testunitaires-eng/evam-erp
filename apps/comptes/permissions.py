"""
Permissions génériques basées sur le profil de l'utilisateur.

Chaque vue déclare explicitement la liste des profils autorisés. Les
règles sont donc directement lisibles dans chaque `views.py` (pas de
table de configuration séparée) - plus simple à auditer, quitte à
devoir modifier le code et redéployer pour changer une règle.

Utilisation dans un viewset :

    from apps.comptes.permissions import role_required
    from apps.comptes.models import Profil

    class OrdreFabricationViewSet(viewsets.ModelViewSet):
        permission_classes = [role_required(
            Profil.RESPONSABLE_PRODUCTION, Profil.ADMIN_SI
        )]
"""

from rest_framework.permissions import BasePermission


def role_required(*profils_autorises):
    """
    Retourne une classe de permission DRF qui n'autorise l'accès
    qu'aux utilisateurs dont le profil figure dans `profils_autorises`.

    Un compte désactivé (is_active=False) est toujours refusé, même
    s'il a un jeton encore valide (double vérification : SimpleJWT
    bloque déjà ces comptes en amont, mais on le revérifie ici par
    prudence pour les autres backends d'authentification éventuels).

    Le superutilisateur a toujours accès.
    """
    profils_autorises = set(profils_autorises)

    class RoleAutorise(BasePermission):
        message = ("Votre profil ne vous autorise pas à effectuer "
                   "cette action sur ce module.")

        def has_permission(self, request, view):
            utilisateur = request.user
            if not utilisateur or not utilisateur.is_authenticated:
                return False
            if not utilisateur.is_active:
                return False
            if utilisateur.is_superuser:
                return True
            return getattr(utilisateur, "profil", None) in profils_autorises

    return RoleAutorise


def lecture_seule_pour(*profils_lecture_seule):
    """
    Retourne une classe de permission qui autorise la lecture (GET) à
    tout utilisateur authentifié et actif, mais restreint l'écriture
    (POST/PUT/PATCH/DELETE) aux profils listés.
    """
    class LectureSeule(BasePermission):
        message = "Ce module est en lecture seule pour votre profil."

        def has_permission(self, request, view):
            utilisateur = request.user
            if not utilisateur or not utilisateur.is_authenticated:
                return False
            if not utilisateur.is_active:
                return False
            if utilisateur.is_superuser:
                return True
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return True
            return getattr(utilisateur, "profil", None) in profils_lecture_seule

    return LectureSeule
