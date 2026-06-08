"""
Serializers for the Research app API.

Model field names are chosen so the global ``djangorestframework-camel-case``
renderer emits exactly the camelCase shape the frontend expects
(e.g. ``enabled_tools`` -> ``enabledTools``, ``standards_template`` ->
``standardsTemplate``).
"""

from rest_framework import serializers

from research.models import ResearchProject


class ResearchProjectSerializer(serializers.ModelSerializer):
    """Read/write serializer for a research project (list + create)."""

    pending_review_count = serializers.SerializerMethodField()
    approved_count = serializers.SerializerMethodField()
    source_count = serializers.SerializerMethodField()

    class Meta:
        model = ResearchProject
        fields = [
            "id",
            "title",
            "question",
            "field",
            "status",
            "enabled_tools",
            "standards_template",
            "pending_review_count",
            "approved_count",
            "source_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "pending_review_count",
            "approved_count",
            "source_count",
            "created_at",
            "updated_at",
        ]

    def get_pending_review_count(self, obj):
        # Wired to staging items in a later increment.
        return 0

    def get_approved_count(self, obj):
        # Wired to approved knowledge items in a later increment.
        return 0

    def get_source_count(self, obj):
        # Wired to the source library in a later increment.
        return 0
