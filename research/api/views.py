"""
ViewSets for the Research app API.
"""

from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from common.permissions import IsResearcherOrAbove
from research.api.serializers import ResearchProjectSerializer
from research.models import ResearchProject


class ResearchProjectViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Research projects owned by the authenticated researcher.

    Endpoints (increment 1):
    - GET  /api/research/projects/  - list the user's projects
    - POST /api/research/projects/  - create a project
    """

    serializer_class = ResearchProjectSerializer
    permission_classes = [IsAuthenticated, IsResearcherOrAbove]

    def get_queryset(self):
        return ResearchProject.active_objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
