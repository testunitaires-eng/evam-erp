"""
Pagination par défaut de l'API.

Paginer une liste sans ordre fixe donne des pages instables (sur
PostgreSQL, une même ligne peut apparaître sur deux pages, une autre
sur aucune). Toute liste qui n'est triée ni par le modèle (Meta.ordering),
ni par la vue, ni par le paramètre ?ordering= est donc triée ici, de la
plus récente à la plus ancienne (clé primaire décroissante).
"""

from rest_framework.pagination import PageNumberPagination


class PaginationOrdonnee(PageNumberPagination):
    def paginate_queryset(self, queryset, request, view=None):
        if hasattr(queryset, "ordered") and not queryset.ordered:
            queryset = queryset.order_by("-pk")
        return super().paginate_queryset(queryset, request, view)
