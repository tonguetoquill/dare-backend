"""
ViewSets for the Research app API.
"""

from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from common.permissions import IsResearcherOrAbove
from research.api.serializers import (
    ResearchProjectDetailSerializer,
    ResearchProjectSerializer,
)
from research.models import ResearchProject


class ResearchProjectViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Research projects owned by the authenticated researcher.

    Endpoints:
    - GET  /api/research/projects/       - list the user's projects
    - POST /api/research/projects/       - create a project
    - GET  /api/research/projects/{id}/  - retrieve a single project
    """

    serializer_class = ResearchProjectSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAbove]

    def get_serializer_class(self):
        # The single-project payload is the workspace aggregation point; it will
        # grow to nest soul file, sources, runs and staging items over time.
        if self.action == "retrieve":
            return ResearchProjectDetailSerializer
        return ResearchProjectSerializer

    def get_queryset(self):
        return ResearchProject.active_objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
