"""What a call to a server's tool comes back as: the text a turn reads, or the failure a
model is told of. A picture or a sound is named, not carried."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.config import MissingEnv
from my_agent_crew.mcp.wire import McpError
from my_agent_crew.tools.registry import ToolError

Call = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _block(block: Any) -> str:
    if not isinstance(block, dict):
        return ""
    kind = block.get("type")
    if kind == "text":
        return str(block.get("text") or "")
    if kind == "resource":
        resource = block.get("resource")
        resource = resource if isinstance(resource, dict) else {}
        text = resource.get("text")
        if isinstance(text, str) and text:
            return text
        return t.MCP_BLOCK.format(kind="resource", detail=resource.get("uri") or "?")
    if kind == "resource_link":
        return t.MCP_BLOCK.format(kind="link", detail=block.get("uri") or "?")
    return t.MCP_BLOCK.format(kind=kind or "?", detail=block.get("mimeType") or "?")


def render(result: dict[str, Any]) -> str:
    """The text of a tool's result. A picture or a sound is named, not carried: a turn
    reads text. A result with no text but with structured content is that content."""
    content = result.get("content")
    parts = [_block(block) for block in content] if isinstance(content, list) else []
    text = "\n".join(part for part in parts if part)
    structured = result.get("structuredContent")
    if not text and structured is not None:
        return json.dumps(structured, ensure_ascii=False)
    return text


def runner(call: Call, remote: str) -> Callable[[dict[str, Any]], Awaitable[str]]:
    """What runs the tool the server knows as `remote`."""

    async def run(arguments: dict[str, Any]) -> str:
        try:
            result = await call(remote, arguments)
        except MissingEnv as exc:
            raise ToolError(t.MCP_MISSING_ENV.format(names=", ".join(exc.names))) from exc
        except McpError as exc:
            raise ToolError(str(exc)) from exc
        text = render(result)
        if result.get("isError"):
            raise ToolError(text or t.MCP_TOOL_FAILED)
        return text or t.MCP_EMPTY_RESULT

    return run
