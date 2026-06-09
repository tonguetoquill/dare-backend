"""
URL routing for the Research API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from research.api.views import (
    ResearchChatView,
    ResearchProjectViewSet,
    ResearchScoutView,
    ResearchSoulFileView,
    ResearchStagingItemReviewView,
)

router = DefaultRouter()
router.register("projects", ResearchProjectViewSet, basename="research-project")

urlpatterns = [
    path(
        "projects/<int:project_id>/chat/",
        ResearchChatView.as_view(),
        name="research-chat",
    ),
    path(
        "projects/<int:project_id>/scout/",
        ResearchScoutView.as_view(),
        name="research-scout",
    ),
    path(
        "projects/<int:project_id>/soul/",
        ResearchSoulFileView.as_view(),
        name="research-soul",
    ),
    path(
        "staging-items/<int:item_id>/review/",
        ResearchStagingItemReviewView.as_view(),
        name="research-staging-review",
    ),
    path("", include(router.urls)),
]
