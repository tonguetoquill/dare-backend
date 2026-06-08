"""
URL routing for the Research API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from research.api.views import ResearchProjectViewSet

router = DefaultRouter()
router.register("projects", ResearchProjectViewSet, basename="research-project")

urlpatterns = [
    path("", include(router.urls)),
]
