"""
Serializers for the Research app API.

Model field names are chosen so the global ``djangorestframework-camel-case``
renderer emits exactly the camelCase shape the frontend expects
(e.g. ``enabled_tools`` -> ``enabledTools``, ``standards_template`` ->
``standardsTemplate``).
"""

from rest_framework import serializers

from research.models import (
    ResearchAgentRun,
    ResearchAgentToolCall,
    ResearchProject,
)


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


class ResearchAgentToolCallSerializer(serializers.ModelSerializer):
    """A single tool invocation within a run (audit)."""

    query = serializers.SerializerMethodField()

    class Meta:
        model = ResearchAgentToolCall
        fields = ["id", "tool", "query", "status", "duration_ms", "result_summary"]
        read_only_fields = fields

    def get_query(self, obj):
        return (obj.arguments or {}).get("query", "")


class ResearchAgentRunSerializer(serializers.ModelSerializer):
    """A delegated run with its tool calls (the Runs/activity record)."""

    tools = serializers.JSONField(source="allowed_tools", read_only=True)
    cost = serializers.FloatField(read_only=True)
    ran_at = serializers.SerializerMethodField()
    staged_count = serializers.SerializerMethodField()
    tool_calls = serializers.SerializerMethodField()

    class Meta:
        model = ResearchAgentRun
        fields = [
            "id",
            "role",
            "mode",
            "task",
            "status",
            "soul_file_version",
            "tools",
            "staged_count",
            "cost",
            "started_at",
            "completed_at",
            "ran_at",
            "hermes_run_id",
            "tool_calls",
        ]
        read_only_fields = fields

    def get_ran_at(self, obj):
        return obj.started_at or obj.created_at

    def get_staged_count(self, obj):
        # Wired to staging items in a later increment.
        return 0

    def get_tool_calls(self, obj):
        calls = ResearchAgentToolCall.active_objects.filter(run=obj).order_by(
            "created_at"
        )
        return ResearchAgentToolCallSerializer(calls, many=True).data


class ResearchProjectDetailSerializer(ResearchProjectSerializer):
    """
    Single-project payload for the workspace (GET /api/research/projects/{id}/).

    The aggregation point for the whole workspace: it nests the project's agent
    runs today and will grow to nest the active soul file, sources, staging/review
    items and memory as those models land — so the frontend can load everything
    the workspace needs from one call.
    """

    runs = serializers.SerializerMethodField()

    class Meta(ResearchProjectSerializer.Meta):
        fields = ResearchProjectSerializer.Meta.fields + ["runs"]

    def get_runs(self, obj):
        runs = ResearchAgentRun.active_objects.filter(project=obj).order_by(
            "-created_at"
        )
        return ResearchAgentRunSerializer(runs, many=True).data
