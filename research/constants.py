"""
Constants for the Research app (Research Mode / the "epistemic ecosystem").

Naming follows the house style: choice groups are plain classes exposing a
``choices()`` classmethod (see ``mcp/constants.py``).

Only ``ResearchProjectStatus`` is enforced at the DB level — it is a workflow
state DARE itself sets. ``StandardsTemplate`` is kept here as a canonical
reference set for the UI/docs. Enabled tools are NOT modelled here: they are
stored as free-form slugs in ``ResearchProject.enabled_tools`` (the user's
connected MCP integrations, plus built-ins like web search), so there is no
hardcoded tool enum to keep in sync.
"""


class ResearchProjectStatus:
    """Workflow status for a ResearchProject (DARE-owned)."""

    ACTIVE = "active"
    ARCHIVED = "archived"

    @classmethod
    def choices(cls):
        return [
            (cls.ACTIVE, "Active"),
            (cls.ARCHIVED, "Archived"),
        ]


class StandardsTemplate:
    """Known soul-file starter templates (free-form; NOT enforced at the DB level)."""

    RESEARCH_ETHICS = "research-ethics"
    EMPIRICAL_RIGOR = "empirical-rigor"
    CUSTOM = "custom"

    @classmethod
    def choices(cls):
        return [
            (cls.RESEARCH_ETHICS, "Research Ethics"),
            (cls.EMPIRICAL_RIGOR, "Empirical Rigor"),
            (cls.CUSTOM, "Custom"),
        ]


class ResearchSessionMode:
    """
    The two delegation modes (DARE-owned, enforced). Each maps 1:1 to a Hermes
    session: a persistent 'scout' session and a persistent 'chat' session per
    project.
    """

    SCOUT = "scout"
    CHAT = "chat"

    @classmethod
    def choices(cls):
        return [
            (cls.SCOUT, "Scout"),
            (cls.CHAT, "Chat"),
        ]


class ResearchSessionStatus:
    """Session lifecycle (DARE-owned, enforced)."""

    ACTIVE = "active"
    ARCHIVED = "archived"

    @classmethod
    def choices(cls):
        return [
            (cls.ACTIVE, "Active"),
            (cls.ARCHIVED, "Archived"),
        ]


class AgentRunStatus:
    """
    Run lifecycle. Produced/advanced by Hermes, so stored free-form (NOT enforced
    at the DB level); this is the canonical set for the UI/docs.
    """

    STARTED = "started"
    RUNNING = "running"
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def choices(cls):
        return [
            (cls.STARTED, "Started"),
            (cls.RUNNING, "Running"),
            (cls.QUEUED, "Queued"),
            (cls.COMPLETED, "Completed"),
            (cls.FAILED, "Failed"),
        ]


class AgentToolCallStatus:
    """Outcome of a single tool call (recorded; stored free-form)."""

    SUCCESS = "success"
    ERROR = "error"

    @classmethod
    def choices(cls):
        return [
            (cls.SUCCESS, "Success"),
            (cls.ERROR, "Error"),
        ]


class SourceType:
    """Kind of source record (free-form; the canonical set for the UI/docs)."""

    UPLOAD = "upload"
    PAPER = "paper"
    BOOK = "book"
    ARTICLE = "article"
    OTHER = "other"

    @classmethod
    def choices(cls):
        return [
            (cls.UPLOAD, "Upload"),
            (cls.PAPER, "Paper"),
            (cls.BOOK, "Book"),
            (cls.ARTICLE, "Article"),
            (cls.OTHER, "Other"),
        ]
