"""
URL routing for the Research API.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from research.api.views import ResearchChatView, ResearchProjectViewSet

router = DefaultRouter()
router.register("projects", ResearchProjectViewSet, basename="research-project")

urlpatterns = [
    path(
        "projects/<int:project_id>/chat/",
        ResearchChatView.as_view(),
        name="research-chat",
    ),
    path("", include(router.urls)),
]
