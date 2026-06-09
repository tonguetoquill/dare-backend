"""
DARE MCP gateway — exposes a user's connected MCP tools to an external agent
(Hermes) over the MCP Streamable HTTP protocol, while credentials and audit stay
in DARE.

Hermes connects once (`hermes mcp add dare --url <gateway>`); every tool from the
user's connected servers (Consensus, Scite, Scholar, …) becomes available,
namespaced `<server>__<tool>`. A tools/call is routed through DARE's existing
executor, which decrypts creds and logs an MCPToolExecution. No creds leave DARE.
"""

import json
import logging

from asgiref.sync import async_to_sync

from mcp.models import UserMCPConnection
from mcp.services.mcp_tool_executor import mcp_tool_executor

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
_SEP = "__"  # namespace separator: <server_slug>__<tool_name>


def list_user_tools(user):
    """Namespaced tool definitions from the user's active connections."""
    tools = []
    connections = UserMCPConnection.all_objects.filter(
        user=user, is_active=True, is_deleted=False
    ).select_related("server")
    for conn in connections:
        slug = conn.server.slug
        for tool in conn.cached_tools or []:
            name = tool.get("name")
            if not name:
                continue
            tools.append(
                {
                    "name": f"{slug}{_SEP}{name}",
                    "description": tool.get("description", "") or "",
                    "inputSchema": tool.get("inputSchema")
                    or tool.get("input_schema")
                    or {"type": "object"},
                }
            )
    return tools


def _result_text(result):
    """Flatten an MCP tool result into plain text (content blocks or JSON)."""
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("text")
            ]
            if parts:
                return "\n".join(parts)
        return json.dumps(result)
    return str(result)


# Common names for a tool's free-text search parameter, in preference order.
_QUERY_PARAM_NAMES = ("query", "term", "q", "search", "keywords", "question")


def _query_param(tool):
    """
    Pick the parameter of `tool` that takes the free-text search query, from its
    input schema. Tools name it differently (Consensus `query`, Scite `term`);
    sending the wrong name silently degrades to an unfiltered search. Returns
    None when the tool has no string parameter to carry a query at all.
    """
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    props = schema.get("properties") or {}
    string_props = [
        name
        for name, spec in props.items()
        if isinstance(spec, dict) and spec.get("type") == "string"
    ]
    for name in _QUERY_PARAM_NAMES:
        if name in string_props:
            return name
    for name in schema.get("required") or []:
        if name in string_props:
            return name
    return string_props[0] if string_props else None


def gather_tool_context(user, slugs, query, per_tool_chars=4000):
    """
    Run the primary tool of each of the user's connected servers whose slug is in
    `slugs`, with {query}, and return a text block of the results — so a delegated
    run (Scout) can draw on credentialed tools (Consensus, …) that DARE executes
    on its behalf. Synchronous (for jobs); best-effort, failures are skipped.
    Credentials and audit stay in DARE (calls go through the executor).
    """
    wanted = {s.lower() for s in (slugs or [])}
    if not wanted:
        return ""
    connections = UserMCPConnection.all_objects.filter(
        user=user, is_active=True, is_deleted=False
    ).select_related("server")
    blocks = []
    for conn in connections:
        slug = conn.server.slug
        if slug.lower() not in wanted:
            continue
        tools = conn.cached_tools or []
        tool = tools[0] if tools else None
        tool_name = tool.get("name") if tool else None
        if not tool_name:
            continue
        param = _query_param(tool)
        if not param:
            logger.warning(
                "gather_tool_context: %s.%s has no string param for a query; skipped",
                slug,
                tool_name,
            )
            continue
        try:
            result = async_to_sync(mcp_tool_executor.execute_tool_call)(
                user, slug, tool_name, {param: query}
            )
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.warning("gather_tool_context %s.%s failed: %s", slug, tool_name, exc)
            continue
        text = _result_text(result).strip()
        if text:
            blocks.append(f"### {slug} · {tool_name}\n{text[:per_tool_chars]}")
    return "\n\n".join(blocks)


def _result(rpc_id, result):
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _error(rpc_id, code, message):
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def handle_jsonrpc(user, payload):
    """
    Handle one MCP JSON-RPC message. Returns the response dict, or None for
    notifications (which take no response).
    """
    method = payload.get("method")
    rpc_id = payload.get("id")

    if method == "initialize":
        return _result(
            rpc_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dare-mcp-gateway", "version": "1.0.0"},
            },
        )

    # Notifications (no id) — acknowledge with no body.
    if rpc_id is None or method == "notifications/initialized":
        return None

    if method == "tools/list":
        return _result(rpc_id, {"tools": list_user_tools(user)})

    if method == "tools/call":
        params = payload.get("params") or {}
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        if _SEP not in name:
            return _error(rpc_id, -32602, f"Unknown tool: {name!r}")
        server_slug, tool_name = name.split(_SEP, 1)
        try:
            result = async_to_sync(mcp_tool_executor.execute_tool_call)(
                user, server_slug, tool_name, arguments
            )
        except Exception as exc:  # noqa: BLE001 - surface as a tool error
            logger.warning("MCP gateway tool %s failed: %s", name, exc)
            return _error(rpc_id, -32000, str(exc))

        # The executor returns the tool result; normalise to MCP content.
        if isinstance(result, dict) and "content" in result:
            return _result(rpc_id, result)
        text = result if isinstance(result, str) else json.dumps(result)
        return _result(rpc_id, {"content": [{"type": "text", "text": text}]})

    return _error(rpc_id, -32601, f"Method not found: {method}")
