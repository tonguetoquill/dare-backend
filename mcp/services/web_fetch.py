"""
Page fetch for the MCP gateway — DARE's own web reader.

The agent runtime's built-in page extraction (Hermes ``web_extract``, Playwright-
backed) proved slow — minutes on some pages. DARE's chat already has a fast,
reliable reader: Anthropic's native ``web_fetch`` server tool (the same one the
"Web Fetch" toggle drives in a normal conversation). The gateway exposes exactly
that, as the builtin ``fetch_page`` tool, so a delegated agent reads pages the
same way the chat does.

Failure is honest: when the page genuinely can't be retrieved (paywall, block,
robots, a fetch error), Anthropic returns a ``web_fetch_tool_error`` with an
``error_code`` — we raise on it rather than passing the model's polite refusal
back as if it were page content. The gateway turns the raised error into a tool
error, so the run's audit shows the call failed instead of a false success.
"""

import logging

from conversations.constants import Provider
from core.services.api_key_service import get_provider_api_key_sync

logger = logging.getLogger(__name__)

# A full paper should come through whole — truncating mid-paper degrades staging
# quality. Runaway cost is contained by the per-run budget, not by chopping.
MAX_CHARS = 40_000
# Cheap model to drive the server-side fetch; the readable text comes from the
# web_fetch tool result, not the model's own knowledge.
WEB_FETCH_MODEL = "claude-haiku-4-5-20251001"
_BETA_HEADER = "web-fetch-2025-09-10"
_TOOL = {
    "type": "web_fetch_20250910",
    "name": "web_fetch",
    "max_uses": 1,
    "citations": {"enabled": False},
    "max_content_tokens": 50_000,
}


class FetchError(Exception):
    """A page genuinely could not be fetched (paywall, block, fetch error)."""


# Anthropic web_fetch error codes -> plain, honest reasons. The wording makes
# clear the failure is THIS page (paywall / block / 404), not a DARE or tool
# outage, so the agent reports it accurately instead of "the tool is down".
_FETCH_REASONS = {
    "url_not_accessible": "the page is blocked, paywalled, or refused the reader",
    "unavailable": "the page is unavailable (paywall, removed, or 404)",
    "too_many_requests": "the site rate-limited the reader",
    "max_uses_exceeded": "the page-fetch budget for this run was reached",
    "unsupported_content_type": "the page is not a readable document",
    "url_not_allowed": "the URL is not on the allowed list",
    "url_too_long": "the URL is too long to fetch",
    "invalid_input": "the URL was rejected as invalid",
}


def _fetch_reason(code):
    """A plain-language reason for an Anthropic web_fetch error code."""
    return _FETCH_REASONS.get(code, f"the reader could not retrieve it ({code})")


def _fetch_result(message):
    """The web_fetch tool-result block as a plain dict, or None. Dicts (via
    model_dump) navigate reliably across SDK versions; nested SDK attribute
    access does not."""
    for block in message.content:
        data = block.model_dump() if hasattr(block, "model_dump") else block
        if isinstance(data, dict) and data.get("type") == "web_fetch_tool_result":
            return data
    return None


def _pdf_text(b64_data):
    """Extract text from a base64 PDF the fetch tool returned (no model needed)."""
    import base64
    import io

    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(base64.b64decode(b64_data)))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _document_text(result):
    """
    Readable text straight from the web_fetch_result document — the fast path.
    The server tool already fetched and parsed the page, so we read its text
    here instead of waiting for the model to re-emit it (which is slow and
    costly). Handles text pages directly and PDFs by local extraction.
    """
    source = ((result.get("content") or {}).get("content") or {}).get("source") or {}
    data = source.get("data")
    if not isinstance(data, str) or not data:
        return ""
    if source.get("type") == "text":
        return data.strip()
    if source.get("type") == "base64" and "pdf" in (source.get("media_type") or ""):
        try:
            return _pdf_text(data)
        except Exception as exc:  # noqa: BLE001 - unreadable PDF; report as a miss
            logger.info("fetch_page PDF extraction failed: %s", exc)
    return ""


def fetch_page(url):
    """
    Return a page's readable text via Anthropic's native ``web_fetch`` tool —
    DARE's chat reader. Raises ``FetchError`` when the page can't be retrieved,
    so the gateway reports a tool error instead of a false success.
    """
    if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
        raise FetchError("'url' must be an http(s) URL.")

    api_key = get_provider_api_key_sync(Provider.CLAUDE.value)
    if not api_key:
        raise FetchError("No Anthropic API key configured for page fetch.")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        message = client.messages.create(
            model=WEB_FETCH_MODEL,
            max_tokens=128,
            tools=[_TOOL],
            extra_headers={"anthropic-beta": _BETA_HEADER},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Use the web_fetch tool to retrieve this URL. Do not "
                        "summarise or repeat the page content — reply with only "
                        f"the word DONE: {url}"
                    ),
                }
            ],
        )
    except anthropic.APIError as exc:
        raise FetchError(f"Page fetch request failed: {exc}") from exc

    result = _fetch_result(message)
    if result is None:
        raise FetchError(f"The reader did not fetch {url}.")

    content = result.get("content") or {}
    if content.get("type") == "web_fetch_tool_error":
        # Anthropic's own failure signal — surface it as a typed, honest reason so
        # the agent reports "this page is paywalled/blocked", never "tool is down".
        code = content.get("error_code", "unavailable")
        raise FetchError(
            f"Could not read {url} — {_fetch_reason(code)} (this page only, not a "
            "tool or system error; try a different source)."
        )

    text = _document_text(result)
    if not text:
        raise FetchError(
            f"Reached {url} but found no readable text — likely a login wall or a "
            "script-only page (this page only, not a tool error)."
        )
    return text[:MAX_CHARS]
