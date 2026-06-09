"""
ViewSets and views for the Research app API.
"""

import json
import logging

from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from djangorestframework_camel_case.render import CamelCaseJSONRenderer
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsResearcherOrAbove
from research.api.serializers import (
    ResearchChatMessageSerializer,
    ResearchProjectDetailSerializer,
    ResearchProjectSerializer,
)
from research.constants import (
    AgentRunStatus,
    AgentToolCallStatus,
    ChatMessageRole,
    ResearchSessionMode,
)
from research.models import (
    ResearchAgentRun,
    ResearchAgentToolCall,
    ResearchChatMessage,
    ResearchProject,
    ResearchSession,
    SoulFile,
)
from research.services import get_hermes_service

logger = logging.getLogger(__name__)


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


class ServerSentEventRenderer(BaseRenderer):
    """Pass-through renderer so DRF content-negotiation accepts SSE requests."""

    media_type = "text/event-stream"
    format = "txt"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


def _sse(payload):
    return f"data: {json.dumps(payload)}\n\n"


class ResearchChatView(APIView):
    """
    Hands-on chat for a project — one persistent chat session, backed by Hermes.

    - GET  /api/research/projects/{id}/chat/  - the chat transcript
    - POST /api/research/projects/{id}/chat/  - send a message; streams the
      assistant reply back as SSE (proxying Hermes `message.delta` events).
    """

    permission_classes = [IsAuthenticated, IsResearcherOrAbove]
    renderer_classes = [CamelCaseJSONRenderer, ServerSentEventRenderer]

    def _get_project(self, request, project_id):
        return get_object_or_404(
            ResearchProject.active_objects, id=project_id, user=request.user
        )

    def get(self, request, project_id):
        project = self._get_project(request, project_id)
        session = ResearchSession.active_objects.filter(
            project=project, mode=ResearchSessionMode.CHAT
        ).first()
        messages = (
            ResearchChatMessage.active_objects.filter(session=session).order_by(
                "created_at"
            )
            if session
            else ResearchChatMessage.objects.none()
        )
        return Response(ResearchChatMessageSerializer(messages, many=True).data)

    def post(self, request, project_id):
        project = self._get_project(request, project_id)
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response(
                {"error": "A non-empty 'message' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = ResearchSession.get_or_create_chat_session(project, request.user)
        soul = SoulFile.active_objects.filter(project=project).first()
        soul_version = soul.current_version() if soul else None
        soul_content = soul_version.content if soul_version else ""
        soul_label = f"v{soul_version.version}" if soul_version else ""

        run = ResearchAgentRun.objects.create(
            session=session,
            project=project,
            user=request.user,
            role="main-assistant",
            mode=ResearchSessionMode.CHAT,
            task=message,
            status=AgentRunStatus.RUNNING,
            soul_file_version=soul_label,
            started_at=timezone.now(),
        )
        ResearchChatMessage.objects.create(
            session=session,
            project=project,
            user=request.user,
            role=ChatMessageRole.USER,
            content=message,
        )

        hermes = get_hermes_service()
        try:
            started = hermes.start_run(
                input_text=message,
                instructions=soul_content,
                session_id=session.hermes_session_id,
            )
            hermes_run_id = started["run_id"]
        except Exception as exc:  # noqa: BLE001 - surface as a failed run
            logger.error("Hermes start_run failed: %s", exc)
            run.status = AgentRunStatus.FAILED
            run.error = str(exc)
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error", "completed_at", "updated_at"])
            return Response(
                {"error": "Could not reach the agent runtime."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        run.hermes_run_id = hermes_run_id
        run.save(update_fields=["hermes_run_id", "updated_at"])

        def event_stream():
            chunks = []
            try:
                for event in hermes.stream_events(hermes_run_id):
                    event_type = event.get("event")
                    if event_type == "message.delta":
                        delta = event.get("delta", "")
                        if delta:
                            chunks.append(delta)
                            yield _sse({"type": "delta", "delta": delta})
                    elif event_type == "tool.started":
                        yield _sse(
                            {
                                "type": "tool",
                                "phase": "started",
                                "tool": event.get("tool", ""),
                            }
                        )
                    elif event_type == "tool.completed":
                        duration = event.get("duration")
                        ResearchAgentToolCall.objects.create(
                            run=run,
                            tool=event.get("tool", ""),
                            status=(
                                AgentToolCallStatus.ERROR
                                if event.get("error")
                                else AgentToolCallStatus.SUCCESS
                            ),
                            duration_ms=(
                                int(duration * 1000) if duration else None
                            ),
                            error=event.get("error") or "",
                        )
                        yield _sse(
                            {
                                "type": "tool",
                                "phase": "completed",
                                "tool": event.get("tool", ""),
                            }
                        )
                    elif event_type == "run.completed":
                        break
            except Exception as exc:  # noqa: BLE001 - mark the run failed
                logger.error("Hermes stream failed for run %s: %s", run.id, exc)
                run.status = AgentRunStatus.FAILED
                run.error = str(exc)
                run.completed_at = timezone.now()
                run.save(
                    update_fields=["status", "error", "completed_at", "updated_at"]
                )
                yield _sse(
                    {"type": "error", "error": "The agent stream was interrupted."}
                )
                return

            assistant_message = ResearchChatMessage.objects.create(
                session=session,
                project=project,
                user=request.user,
                role=ChatMessageRole.ASSISTANT,
                content="".join(chunks),
                run=run,
            )
            run.status = AgentRunStatus.COMPLETED
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "completed_at", "updated_at"])
            session.last_run_at = timezone.now()
            session.save(update_fields=["last_run_at", "updated_at"])
            yield _sse(
                {
                    "type": "done",
                    "messageId": assistant_message.id,
                    "runId": run.id,
                }
            )

        response = StreamingHttpResponse(
            event_stream(), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
