from django.contrib import admin
from .models import SequenceNumerotation


@admin.register(SequenceNumerotation)
class SequenceNumerotationAdmin(admin.ModelAdmin):
    list_display = ("prefixe", "dernier_numero")
