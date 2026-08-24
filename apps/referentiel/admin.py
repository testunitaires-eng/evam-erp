"""
Interface d'administration Django du module referentiel.

Accessible sur /admin/ - pratique pour vérifier ou corriger des
données rapidement sans passer par l'API, réservé en pratique à
l'Administrateur SI (superutilisateur Django).
"""

from django.contrib import admin
from . import models

@admin.register(models.Article)
class ArticleAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.FicheTechnique)
class FicheTechniqueAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.CompositionFicheTechnique)
class CompositionFicheTechniqueAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.FicheConditionnement)
class FicheConditionnementAdmin(admin.ModelAdmin):
    search_fields = ()

