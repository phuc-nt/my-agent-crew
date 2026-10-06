"""What an MCP server lists, as tools of the crew.

A server's tool is a tool like any other once it is here: it goes through the same
registry, the same approval gate and the same shaping of long output. What sets it apart is
kept on it: the server it belongs to, the name the server knows it by, and how far it is
let in. Whether it asks first is the owner's call alone. A server may say a tool only
reads; that is shown beside the tool and decides nothing, because the one saying it is the
one being trusted.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts_mcp as t
from my_agent_crew.mcp.config import DEFERRED, DIRECT, McpServer, MissingEnv
from my_agent_crew.mcp.wire import McpError
from my_agent_crew.tools.registry import Tool, ToolError

PREFIX = "mcp__"
# The longest name every provider accepts for a tool.
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 2000
# A tool's description where it is one line of a list.
SUMMARY_CHARS = 200
HASH_CHARS = 8
EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

Call = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class McpTool(Tool):
    server: str = ""
    # The tool's name on its server, which is what a call names.
    remote: str = ""
    exposure: str = DEFERRED
    # What the server says of it. Shown, never acted on.
    read_only_hint: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "server": self.server, "exposure": self.exposure}


@dataclass(frozen=True)
class CompanionTool(Tool):
    """A tool that comes with an agent's servers instead of from its own list: the one
    that finds their tools, and the one that calls them from a script."""

    def to_dict(self) -> dict[str, Any]:
        # For the owner's screens: it follows the servers, not the agent's allow-list.
        return {**super().to_dict(), "with_mcp": True}


def held_back(tool: Tool | None) -> bool:
    """Not told to the model up front: the agent holds it, and finds it with `tool_search`."""
    return isinstance(tool, McpTool) and tool.exposure != DIRECT


def summary(description: str) -> str:
    line = " ".join(description.split())
    return line if len(line) <= SUMMARY_CHARS else line[: SUMMARY_CHARS - 1] + "…"


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", text)


def tool_name(server: str, tool: str) -> str:
    """`mcp__<server>__<tool>`, in the letters a provider accepts. A name too long is cut
    and closed with a digest of the tool's own name, so two long names do not meet."""
    name = f"{PREFIX}{_safe(server)}__{_safe(tool)}"
    if len(name) <= MAX_NAME_CHARS:
        return name
    digest = hashlib.sha256(tool.encode("utf-8")).hexdigest()[:HASH_CHARS]
    return f"{name[: MAX_NAME_CHARS - HASH_CHARS - 1]}_{digest}"


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


def _runner(call: Call, remote: str) -> Callable[[dict[str, Any]], Awaitable[str]]:
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


def _schema(raw: Any) -> dict[str, Any]:
    # A provider refuses a tool whose parameters are not an object.
    if isinstance(raw, dict) and raw.get("type") == "object":
        return raw
    return EMPTY_SCHEMA


def _description(server: McpServer, raw: dict[str, Any]) -> str:
    said = raw.get("description")
    said = said.strip() if isinstance(said, str) else ""
    if len(said) > MAX_DESCRIPTION_CHARS:
        said = said[: MAX_DESCRIPTION_CHARS - 1] + "…"
    return t.MCP_DESCRIPTION.format(server=server.name, description=said or raw["name"])


def build_tools(
    server: McpServer, listed: Sequence[dict[str, Any]], call: Call
) -> tuple[tuple[McpTool, ...], tuple[str, ...]]:
    """(the server's tools, the names left out). A tool is left out when another already
    took the name it comes to here; one that is hidden is built, so the owner sees it
    listed, and is kept from the agents where they are handed their tools."""
    tools: dict[str, McpTool] = {}
    skipped: list[str] = []
    for raw in listed:
        remote = raw.get("name") if isinstance(raw, dict) else None
        if not isinstance(remote, str) or not remote:
            continue
        name = tool_name(server.name, remote)
        if name in tools:
            skipped.append(remote)
            continue
        reads = server.reads_only(remote)
        annotations = raw.get("annotations")
        tools[name] = McpTool(
            name=name,
            description=_description(server, raw),
            parameters=_schema(raw.get("inputSchema")),
            run=_runner(call, remote),
            requires_approval=not reads,
            replay_safe=reads,
            server=server.name,
            remote=remote,
            exposure=server.exposure_of(remote),
            read_only_hint=isinstance(annotations, dict)
            and annotations.get("readOnlyHint") is True,
        )
    return tuple(tools.values()), tuple(skipped)
