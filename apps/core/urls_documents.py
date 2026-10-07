from django.urls import path
from . import views_documents

urlpatterns = [
    path("entreprise/", views_documents.entreprise, name="documents-entreprise"),
    path("entreprise/logo/", views_documents.logo, name="documents-logo"),
    path("apercu/", views_documents.apercu, name="documents-apercu"),
]
