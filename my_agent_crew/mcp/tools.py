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
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts_mcp as t
from my_agent_crew.llm.types import ToolSpec
from my_agent_crew.mcp.config import DEFERRED, DIRECT, McpServer
from my_agent_crew.mcp.tool_limits import NAME_TAKEN, Folded, shown, unfit
from my_agent_crew.mcp.tool_result import Call, runner
from my_agent_crew.tools.registry import Tool

PREFIX = "mcp__"
# The longest name every provider accepts for a tool.
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 2000
# A tool's description where it is one line of a list.
SUMMARY_CHARS = 200
HASH_CHARS = 8
EMPTY_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpTool(Tool):
    server: str = ""
    # The tool's name on its server, which is what a call names.
    remote: str = ""
    exposure: str = DEFERRED
    # What the server says of it. Shown, never acted on.
    read_only_hint: bool = False
    # Its parameters as a model is told them, where the server's own were too long to
    # send. `parameters` stays what the server wrote, and is what everything here reads.
    folded: Folded | None = None

    @property
    def spec(self) -> ToolSpec:
        told = self.folded.schema if self.folded else self.parameters
        return ToolSpec(name=self.name, description=self.description, parameters=told)

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "server": self.server, "exposure": self.exposure}


@dataclass(frozen=True)
class CompanionTool(Tool):
    """A tool that comes with an agent's servers instead of from its own list: the one
    that finds their tools."""

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
    """(the server's tools, the names left out). A tool is left out when it is more than
    is taken (`tool_limits`) or another already took the name it comes to here; one that
    is hidden is built, so the owner sees it listed, and is kept from the agents where
    they are handed their tools. One whose parameters fit only folded is taken, and said
    to be in the log."""
    tools: dict[str, McpTool] = {}
    skipped: list[str] = []
    for raw in listed:
        remote = raw.get("name") if isinstance(raw, dict) else None
        if not isinstance(remote, str) or not remote:
            continue
        schema = _schema(raw.get("inputSchema"))
        why, folded = unfit(remote, schema)
        name = "" if why else tool_name(server.name, remote)
        if name in tools:
            why = NAME_TAKEN
        if why:
            skipped.append(shown(remote))
            # %r: a name is the server's to choose, line breaks and all.
            logger.warning("MCP server %s: tool %r left out, %s", server.name, skipped[-1], why)
            continue
        if folded:
            logger.info(
                "MCP server %s: tool %r parameters folded, %d chars to %d",
                server.name,
                remote,
                folded.before,
                folded.after,
            )
        reads = server.reads_only(remote)
        annotations = raw.get("annotations")
        tools[name] = McpTool(
            name=name,
            description=_description(server, raw),
            parameters=schema,
            run=runner(call, remote),
            requires_approval=not reads,
            replay_safe=reads,
            server=server.name,
            remote=remote,
            exposure=server.exposure_of(remote),
            read_only_hint=isinstance(annotations, dict)
            and annotations.get("readOnlyHint") is True,
            folded=folded,
        )
    return tuple(tools.values()), tuple(skipped)
