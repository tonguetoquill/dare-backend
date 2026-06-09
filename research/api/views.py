"""
ViewSets and views for the Research app API.
"""

import json
import logging
import time

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
    ResearchStagingItemSerializer,
)
from research.constants import (
    AgentRunStatus,
    AgentToolCallStatus,
    ChatMessageRole,
    ResearchSessionMode,
    SoulFileOrigin,
    StagingItemStatus,
)
from research.models import (
    ResearchAgentRun,
    ResearchAgentToolCall,
    ResearchChatMessage,
    ResearchKnowledgeItem,
    ResearchProject,
    ResearchSession,
    ResearchStagingItem,
    SoulFile,
    SoulFileVersion,
)
from research.services import (
    build_scout_instructions,
    get_hermes_service,
    parse_staging_items,
)

logger = logging.getLogger(__name__)


class ResearchProjectViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Research projects owned by the authenticated researcher.

    Endpoints:
    - GET   /api/research/projects/       - list the user's projects
    - POST  /api/research/projects/       - create a project
    - GET   /api/research/projects/{id}/  - retrieve a single project
    - PATCH /api/research/projects/{id}/  - update a project
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
                            duration_ms=(int(duration * 1000) if duration else None),
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


class ResearchScoutView(APIView):
    """
    Delegated Scout discovery for a project.

    POST /api/research/projects/{id}/scout/  — runs Scout on Hermes (web search),
    waits for it to finish, and persists the returned source candidates as staging
    items (status='staged') with full provenance. They then appear in the Review
    Inbox. Returns {runId, stagedCount}.
    """

    permission_classes = [IsAuthenticated, IsResearcherOrAbove]

    def post(self, request, project_id):
        project = get_object_or_404(
            ResearchProject.active_objects, id=project_id, user=request.user
        )
        task = (request.data.get("task") or request.data.get("query") or "").strip()
        if not task:
            return Response(
                {"error": "A non-empty 'task' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = ResearchSession.get_or_create_scout_session(project, request.user)
        soul = SoulFile.active_objects.filter(project=project).first()
        version = soul.current_version() if soul else None
        soul_content = version.content if version else ""
        soul_label = f"v{version.version}" if version else ""

        run = ResearchAgentRun.objects.create(
            session=session,
            project=project,
            user=request.user,
            role="scout",
            mode=ResearchSessionMode.SCOUT,
            task=task,
            status=AgentRunStatus.RUNNING,
            soul_file_version=soul_label,
            allowed_tools=["web"],
            started_at=timezone.now(),
        )

        hermes = get_hermes_service()
        try:
            started = hermes.start_run(
                input_text=task,
                instructions=build_scout_instructions(soul_content),
                session_id=session.hermes_session_id,
            )
            hermes_run_id = started["run_id"]
        except Exception as exc:  # noqa: BLE001
            logger.error("Hermes start_run (scout) failed: %s", exc)
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

        # Scout runs are long, so poll Hermes to completion and persist the
        # results here. A normal view runs to completion server-side even if the
        # client disconnects, so finalisation is reliable. (Production should move
        # this to a background worker — django-rq — per the §4 "runs are long" note.)
        info = None
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            try:
                info = hermes.get_run(hermes_run_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Hermes poll failed for run %s: %s", run.id, exc)
                break
            if info.get("status") in ("completed", "failed"):
                break
            time.sleep(3)

        if not info or info.get("status") != "completed":
            run.status = AgentRunStatus.FAILED
            run.error = (info or {}).get("status") or "timed out"
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error", "completed_at", "updated_at"])
            return Response(
                {"error": "Scout did not finish in time.", "runId": run.id},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        # Log tool calls (provenance) — best-effort replay of the event stream.
        try:
            for event in hermes.stream_events(hermes_run_id):
                if event.get("event") == "tool.completed":
                    duration = event.get("duration")
                    ResearchAgentToolCall.objects.create(
                        run=run,
                        tool=event.get("tool", ""),
                        arguments={"query": task},
                        status=(
                            AgentToolCallStatus.ERROR
                            if event.get("error")
                            else AgentToolCallStatus.SUCCESS
                        ),
                        duration_ms=int(duration * 1000) if duration else None,
                        error=event.get("error") or "",
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read scout tool events for %s: %s", run.id, exc)

        now = timezone.now()
        staged = 0
        for item in parse_staging_items(info.get("output", "")):
            year = item.get("year")
            confidence = item.get("confidence")
            try:
                ResearchStagingItem.objects.create(
                    project=project,
                    run=run,
                    title=str(item.get("title") or "")[:512],
                    authors=str(item.get("authors") or "")[:512],
                    year=year if isinstance(year, int) else None,
                    venue=str(item.get("venue") or "")[:255],
                    doi=str(item.get("doi") or "")[:255],
                    url=str(item.get("url") or "")[:1024],
                    rationale=str(item.get("rationale") or ""),
                    confidence=(
                        float(confidence)
                        if isinstance(confidence, (int, float))
                        else None
                    ),
                    confidence_rationale=str(item.get("confidenceRationale") or ""),
                    evidence_label=str(item.get("evidenceLabel") or "")[:32],
                    citation_context=str(item.get("citationContext") or ""),
                    status=StagingItemStatus.STAGED,
                    provenance={
                        "tool": "web",
                        "query": task,
                        "retrievedAt": now.isoformat(),
                        "soulFileId": soul.id if soul else None,
                        "soulFileVersion": version.version if version else None,
                        "role": "scout",
                        "runId": run.id,
                    },
                )
                staged += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("Scout staging item create failed: %s", exc)

        run.status = AgentRunStatus.COMPLETED
        run.completed_at = now
        run.save(update_fields=["status", "completed_at", "updated_at"])
        session.last_run_at = now
        session.save(update_fields=["last_run_at", "updated_at"])
        return Response({"runId": run.id, "stagedCount": staged})


class ResearchStagingItemReviewView(APIView):
    """
    Scholar review of a staged candidate.

    POST /api/research/staging-items/{id}/review/  body {decision, reason?}
    - approve -> promote to a ResearchKnowledgeItem (the durability gate)
    - reject  -> status rejected (+ reason)
    - later   -> status later   (+ reason)
    """

    permission_classes = [IsAuthenticated, IsResearcherOrAbove]

    def post(self, request, item_id):
        item = get_object_or_404(
            ResearchStagingItem.active_objects,
            id=item_id,
            project__user=request.user,
        )
        decision = (request.data.get("decision") or "").strip()
        reason = (request.data.get("reason") or "").strip()

        if decision == "approve":
            ResearchKnowledgeItem.objects.create(
                project=item.project,
                source_staging_item=item,
                approved_by=request.user,
                approved_at=timezone.now(),
                content=item.content or item.rationale,
                rationale=item.rationale,
                provenance=item.provenance,
                soul_file_version=str(
                    (item.provenance or {}).get("soulFileVersion") or ""
                ),
            )
            item.status = StagingItemStatus.APPROVED
            item.save(update_fields=["status", "updated_at"])
        elif decision == "reject":
            item.status = StagingItemStatus.REJECTED
            item.rejection_reason = reason
            item.save(update_fields=["status", "rejection_reason", "updated_at"])
        elif decision == "later":
            item.status = StagingItemStatus.LATER
            item.later_reason = reason
            item.save(update_fields=["status", "later_reason", "updated_at"])
        else:
            return Response(
                {"error": "decision must be one of: approve, reject, later."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(ResearchStagingItemSerializer(item).data)


class ResearchSoulFileView(APIView):
    """
    The project's versioned soul file (standards).

    - GET /api/research/projects/{id}/soul/  - the current version
    - PUT /api/research/projects/{id}/soul/  {content, changeNote?} - write a new
      version (the old one is kept; staging items keep the version that governed
      them).
    """

    permission_classes = [IsAuthenticated, IsResearcherOrAbove]

    def _project(self, request, project_id):
        return get_object_or_404(
            ResearchProject.active_objects, id=project_id, user=request.user
        )

    def _serialize(self, soul):
        version = soul.current_version() if soul else None
        if not version:
            return None
        return {
            "id": soul.id,
            "version": version.version,
            "content": version.content,
            "origin": version.origin,
            "updatedAt": version.created_at,
        }

    def get(self, request, project_id):
        project = self._project(request, project_id)
        soul = SoulFile.active_objects.filter(project=project).first()
        return Response(self._serialize(soul))

    def put(self, request, project_id):
        project = self._project(request, project_id)
        content = request.data.get("content")
        if content is None:
            return Response(
                {"error": "'content' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        change_note = request.data.get("change_note") or ""
        soul, _ = SoulFile.objects.get_or_create(project=project)
        latest = (
            SoulFileVersion.active_objects.filter(soul_file=soul)
            .order_by("-version")
            .first()
        )
        SoulFileVersion.objects.create(
            soul_file=soul,
            version=(latest.version + 1) if latest else 1,
            content=content,
            origin=SoulFileOrigin.EDIT,
            change_note=change_note,
            created_by=request.user,
        )
        return Response(self._serialize(soul))
