"""
Scout delegation helpers — how DARE asks Hermes to find sources and how it reads
the result back.

The contract: DARE sends the task as the run `input` and the soul file + a Scout
brief as `instructions`. Scout uses Hermes's `web_search` tool and returns a single
JSON object of source candidates, which DARE parses into staging items.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

SCOUT_BRIEF = """You are Scout, a research source-finder working under the scholar's standards above.

Use the web_search tool to find real, relevant, recent sources for the task. Be
efficient: run AT MOST 3 web searches, then stop and report. Never fabricate —
only include sources you actually found via web_search.

Return ONLY a single JSON object — no prose, no markdown code fences — shaped exactly:
{"stagingItems": [
  {
    "title": "string",
    "authors": "string, semicolon-separated",
    "year": 2024,
    "venue": "string",
    "url": "string",
    "rationale": "why this source matters for the task",
    "confidence": 0.0,
    "confidenceRationale": "why this confidence level",
    "evidenceLabel": "supporting | disputing | partial | tangential | unverifiable",
    "citationContext": "a short relevant quote/context when available"
  }
]}
Return %(max_candidates)d items at most. `confidence` is a number from 0.0 to 1.0."""


def build_scout_instructions(soul_content, max_candidates=4):
    """Compose the run instructions: the soul file (standards) + the Scout brief."""
    parts = []
    if soul_content and soul_content.strip():
        parts.append("# Research standards (soul file)\n" + soul_content.strip())
    parts.append(SCOUT_BRIEF % {"max_candidates": max_candidates})
    return "\n\n".join(parts)


def parse_staging_items(output):
    """
    Extract the `stagingItems` array from Scout's output, tolerating stray prose
    or markdown fences. Returns a list of dicts (empty if nothing parseable).
    """
    if not output:
        return []
    text = output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    data = None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                logger.warning("Scout output was not JSON-parseable")
                return []

    if not isinstance(data, dict):
        return []
    items = data.get("stagingItems", [])
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []
