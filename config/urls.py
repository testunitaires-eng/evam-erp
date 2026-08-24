"""
URL principales du projet EVAM Backend.

Chaque module métier expose ses routes sous /api/<module>/, ce qui
correspond directement aux modules du cahier des charges. La
documentation interactive de l'API est disponible sur /api/docs/.
"""

from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentification par jeton JWT
    path("api/auth/connexion/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/auth/rafraichir/", TokenRefreshView.as_view(), name="token_refresh"),

    # Documentation interactive de l'API
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),

    # Modules métier (correspondance directe avec le cahier des charges)
    path("api/comptes/", include("apps.comptes.urls")),
    path("api/referentiel/", include("apps.referentiel.urls")),
    path("api/achats/", include("apps.achats.urls")),
    path("api/stocks/", include("apps.stocks.urls")),
    path("api/production/", include("apps.production.urls")),
    path("api/qualite/", include("apps.qualite.urls")),
    path("api/commercial/", include("apps.commercial.urls")),
    path("api/caisse/", include("apps.caisse.urls")),
    path("api/distribution/", include("apps.distribution.urls")),
    path("api/couts/", include("apps.couts.urls")),
    path("api/comptabilite/", include("apps.comptabilite.urls")),
]
