"""
Research Mode models (the "epistemic ecosystem").

DARE owns the durable truth: projects, soul files, sources, staging, approved
knowledge, and audit. Agents (later, via Hermes) write to staging only; the
scholar promotes staged items to durable knowledge.

Models land incrementally. This module currently defines:
- ResearchProject: a single line of scholarly inquiry, owned by a researcher.
"""

from django.conf import settings
from django.db import models

from common.managers import ActiveObjectsManager
from common.models import BaseModel
from research.constants import (
    AgentRunStatus,
    AgentToolCallStatus,
    ResearchProjectStatus,
    ResearchSessionMode,
    ResearchSessionStatus,
)


class ResearchProject(BaseModel):
    """
    A single line of scholarly inquiry owned by a researcher.

    Acts as the container for the project's soul files, sources, staging items,
    agent runs, and approved knowledge (added in later increments).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_projects",
        help_text="The researcher (scholar) who owns this project.",
    )
    title = models.CharField(
        max_length=255,
        help_text="Human-readable project title.",
    )
    question = models.TextField(
        blank=True,
        help_text="The central research question driving this project.",
    )
    field = models.CharField(
        max_length=255,
        blank=True,
        help_text="Field or domain of inquiry (e.g. 'Bioethics').",
    )
    status = models.CharField(
        max_length=32,
        choices=ResearchProjectStatus.choices(),
        default=ResearchProjectStatus.ACTIVE,
        help_text="Project workflow status (DARE-owned).",
    )
    enabled_tools = models.JSONField(
        default=list,
        blank=True,
        help_text="Research tool keys enabled for this project (free-form list of strings).",
    )
    standards_template = models.CharField(
        max_length=64,
        blank=True,
        help_text="Soul-file starter template chosen at creation (e.g. 'research-ethics').",
    )

    objects = models.Manager()
    active_objects = ActiveObjectsManager()

    class Meta:
        verbose_name = "Research Project"
        verbose_name_plural = "Research Projects"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.user_id})"


class ResearchSession(BaseModel):
    """
    A delegation context that maps 1:1 to a Hermes session.

    Each project has (at most) one persistent session per mode — a 'scout'
    session for delegated discovery and a 'chat' session for hands-on work — so
    Hermes keeps separate cross-run memory per mode. Agent runs hang off a
    session.
    """

    project = models.ForeignKey(
        ResearchProject,
        on_delete=models.CASCADE,
        related_name="sessions",
        help_text="Project this session belongs to.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_sessions",
        help_text="Scholar who owns this session.",
    )
    mode = models.CharField(
        max_length=16,
        choices=ResearchSessionMode.choices(),
        help_text="Delegation mode (DARE-owned): 'scout' or 'chat'.",
    )
    hermes_session_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Correlating Hermes session id (set when Hermes is wired).",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional human label (e.g. a chat session name).",
    )
    status = models.CharField(
        max_length=16,
        choices=ResearchSessionStatus.choices(),
        default=ResearchSessionStatus.ACTIVE,
        help_text="Session lifecycle (DARE-owned).",
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the most recent run in this session.",
    )

    objects = models.Manager()
    active_objects = ActiveObjectsManager()

    class Meta:
        verbose_name = "Research Session"
        verbose_name_plural = "Research Sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.project_id} · {self.mode}"


class ResearchAgentRun(BaseModel):
    """
    One delegated run from DARE to Hermes; the durable audit record behind the
    Runs/activity view. Hangs off a ResearchSession and maps 1:1 to a Hermes run.

    Runs can be seeded manually for now; the Hermes adapter populates them later.
    """

    session = models.ForeignKey(
        ResearchSession,
        on_delete=models.CASCADE,
        related_name="runs",
        help_text="Session this run belongs to.",
    )
    project = models.ForeignKey(
        ResearchProject,
        on_delete=models.CASCADE,
        related_name="agent_runs",
        help_text="Project this run belongs to (denormalised for filtering).",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="research_agent_runs",
        help_text="Scholar who initiated the run.",
    )
    role = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Agent role slug (e.g. 'scout', 'critic'); free-form for now.",
    )
    mode = models.CharField(
        max_length=16,
        choices=ResearchSessionMode.choices(),
        help_text="Mode of this run, mirroring the session mode.",
    )
    task = models.TextField(
        blank=True,
        default="",
        help_text="The delegated task text.",
    )
    status = models.CharField(
        max_length=32,
        default=AgentRunStatus.STARTED,
        help_text="Run lifecycle (Hermes-produced; free-form).",
    )
    soul_file_version = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Soul file version that governed this run (provenance).",
    )
    selected_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Explicitly chosen context: sourceIds, approvedKnowledgeIds, "
        "projectMemoryIds, conversationIds.",
    )
    allowed_tools = models.JSONField(
        default=list,
        blank=True,
        help_text="Tool slugs this run was allowed to use.",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the run started.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the run finished (null while running).",
    )
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=0,
        help_text="Cumulative cost for the run.",
    )
    error = models.TextField(
        blank=True,
        default="",
        help_text="Error detail if the run failed.",
    )
    hermes_run_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Correlating Hermes run id (set when Hermes is wired).",
    )

    objects = models.Manager()
    active_objects = ActiveObjectsManager()

    class Meta:
        verbose_name = "Research Agent Run"
        verbose_name_plural = "Research Agent Runs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.role or 'run'} · {self.status} ({self.project_id})"


class ResearchAgentToolCall(BaseModel):
    """Audit record for a single tool invocation within a run."""

    run = models.ForeignKey(
        ResearchAgentRun,
        on_delete=models.CASCADE,
        related_name="tool_calls",
        help_text="Run this tool call belongs to.",
    )
    tool = models.CharField(
        max_length=128,
        help_text="Tool/MCP slug invoked (e.g. 'consensus').",
    )
    arguments = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arguments passed to the tool (includes the query).",
    )
    status = models.CharField(
        max_length=16,
        default=AgentToolCallStatus.SUCCESS,
        help_text="Outcome: 'success' or 'error' (free-form).",
    )
    result_summary = models.TextField(
        blank=True,
        default="",
        help_text="Brief summary of the result.",
    )
    duration_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Duration of the call in milliseconds.",
    )
    error = models.TextField(
        blank=True,
        default="",
        help_text="Error detail if the call failed.",
    )

    objects = models.Manager()
    active_objects = ActiveObjectsManager()

    class Meta:
        verbose_name = "Research Agent Tool Call"
        verbose_name_plural = "Research Agent Tool Calls"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.tool} · {self.status}"
