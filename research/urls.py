"""
URL configuration for the Research app.
"""

from django.urls import include, path

app_name = "research"

urlpatterns = [
    path("api/research/", include("research.api.urls")),
]
