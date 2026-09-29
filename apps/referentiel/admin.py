
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

    def save_model(self, request, obj, form, change):
        """Même règle que l'API : un produit fini reçoit sa fiche de composition (brouillon)."""
        super().save_model(request, obj, form, change)
        obj.creer_fiche_technique_brouillon(request.user)


class CompositionFicheTechniqueInline(admin.TabularInline):
    model = models.CompositionFicheTechnique
    extra = 1


@admin.register(models.FicheTechnique)
class FicheTechniqueAdmin(admin.ModelAdmin):
    search_fields = ()
    inlines = [CompositionFicheTechniqueInline]


@admin.register(models.CompositionFicheTechnique)
class CompositionFicheTechniqueAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.FicheConditionnement)
class FicheConditionnementAdmin(admin.ModelAdmin):
    search_fields = ()


@admin.register(models.ControleQualiteRequis)
class ControleQualiteRequisAdmin(admin.ModelAdmin):
    search_fields = ()