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
