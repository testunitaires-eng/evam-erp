"""
Configuration du projet EVAM Backend.

Ce fichier centralise tous les réglages Django. Les valeurs sensibles
(clé secrète, mot de passe base de données, etc.) sont lues depuis un
fichier .env grâce à python-dotenv — voir .env.example à la racine.
"""

import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Dossier racine du projet
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Sécurité ---------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "cle-de-developpement-a-changer-en-production")
DEBUG = os.getenv("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# --- Applications -------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Bibliothèques tierces
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_filters",
    "drf_spectacular",

    # Applications métier EVAM (un module = un "acteur principal"
    # du cahier des charges, voir README.md)
    "apps.core",            # Utilitaires transverses (numérotation, etc.)
    "apps.comptes",        # Module 12 - Utilisateurs, profils, droits
    "apps.referentiel",    # Module 2  - Articles, fiches techniques, conditionnement
    "apps.achats",         # Module 3  - Fournisseurs, besoins, commandes fournisseurs
    "apps.stocks",         # Module 4  - Mouvements, dépôts, inventaires
    "apps.production",     # Module 5  - Plan de production, OF, sorties matières
    "apps.qualite",        # Module 6  - Lots, contrôle qualité, traçabilité
    "apps.commercial",     # Module 7  - Clients, commandes, factures, tarifs
    "apps.caisse",         # Module 8  - Sessions de caisse, encaissements
    "apps.distribution",   # Module 9  - Préparation, tournées, livraisons
    "apps.couts",          # Module 10 - Coûts standards/réels, rentabilité
    "apps.comptabilite",   # Module 11 - Pilotage, anomalies, exports comptables
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Base de données ------------------------------------------------
# Par défaut : SQLite pour démarrer rapidement en développement.
# En production, définir DATABASE_URL (ex. postgres://user:pass@host:5432/nom_bdd)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --- Utilisateur personnalisé -----------------------------------------
AUTH_USER_MODEL = "comptes.Utilisateur"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation ----------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Brazzaville"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST Framework ---------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "API EVAM - Logiciel intégré de gestion",
    "DESCRIPTION": "API du backend EVAM (Groupe 2I) : production, stocks, achats, "
                    "qualité, commercial, caisse, distribution, coûts, comptabilité.",
    "VERSION": "1.0.0",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
}

CORS_ALLOW_ALL_ORIGINS = DEBUG  # à restreindre explicitement en production

LOGIN_REDIRECT_URL = "/admin/"
