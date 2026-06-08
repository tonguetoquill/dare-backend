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
from research.constants import ResearchProjectStatus


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
