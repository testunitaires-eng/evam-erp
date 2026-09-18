
# """
# Interface d'administration Django du module référentiel.
# """

# from django.contrib import admin
# from . import models

# @admin.register(models.Article)
# class ArticleAdmin(admin.ModelAdmin):
#     search_fields = ()


# @admin.register(models.FicheTechnique)
# class FicheTechniqueAdmin(admin.ModelAdmin):
#     search_fields = ()


# @admin.register(models.CompositionFicheTechnique)
# class CompositionFicheTechniqueAdmin(admin.ModelAdmin):
#     search_fields = ()


# @admin.register(models.FicheConditionnement)
# class FicheConditionnementAdmin(admin.ModelAdmin):
#     search_fields = ()


# @admin.register(models.ControleQualiteRequis)
# class ControleQualiteRequisAdmin(admin.ModelAdmin):
#     search_fields = ()



"""
Interface d'administration Django du module référentiel.
"""

from django.contrib import admin
from . import models

@admin.register(models.FamilleArticle)
class FamilleArticleAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.FormatArticle)
class FormatArticleAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.Parfum)
class ParfumAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.UniteVenteArticle)
class UniteVenteArticleAdmin(admin.ModelAdmin):
    search_fields = ()


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


@admin.register(models.ControleQualiteRequis)
class ControleQualiteRequisAdmin(admin.ModelAdmin):
    search_fields = ()