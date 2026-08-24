"""
Permissions génériques basées sur le profil de l'utilisateur.

Plutôt que de dupliquer la logique dans chaque module, on génère
dynamiquement des classes de permission DRF à partir de la liste des
profils autorisés. C'est ce fichier qui traduit en code les règles du
cahier des charges comme :

    "Le magasinier ne peut pas modifier un OF ou des prix"
    "Seuls les lots Libérés sont vendables"
    "Le caissier ne peut pas supprimer un écart, il doit le justifier"

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

    Le superutilisateur (Administrateur SI technique via Django admin)
    a toujours accès, pour ne jamais se retrouver bloqué en cas
    d'incident.
    """
    profils_autorises = set(profils_autorises)

    class RoleAutorise(BasePermission):
        message = ("Votre profil ne vous autorise pas à effectuer "
                   "cette action sur ce module.")

        def has_permission(self, request, view):
            utilisateur = request.user
            if not utilisateur or not utilisateur.is_authenticated:
                return False
            if utilisateur.is_superuser:
                return True
            return getattr(utilisateur, "profil", None) in profils_autorises

    return RoleAutorise


def lecture_seule_pour(*profils_lecture_seule):
    """
    Retourne une classe de permission qui autorise la lecture (GET)
    à tout utilisateur authentifié, mais restreint l'écriture
    (POST/PUT/PATCH/DELETE) aux profils listés.

    Exemple : le Commercial "consulte le stock disponible (pas de
    modification stock)" -> StockArticleViewSet utilise cette
    permission avec profils_lecture_seule vide pour l'écriture
    réservée aux Magasiniers/Administrateurs.
    """
    class LectureSeule(BasePermission):
        message = "Ce module est en lecture seule pour votre profil."

        def has_permission(self, request, view):
            utilisateur = request.user
            if not utilisateur or not utilisateur.is_authenticated:
                return False
            if utilisateur.is_superuser:
                return True
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return True
            return getattr(utilisateur, "profil", None) in profils_lecture_seule

    return LectureSeule
