"""Which of an agent's tools a model call is told of.

Every built-in is told, and so is an MCP tool the owner let in as `direct`. The other MCP
tools are held back: a server can list dozens, each with a schema, and telling them all
would be paid for on every call of every turn. They are still the agent's, and still run
when called by name.
"""

from __future__ import annotations

from my_agent_crew.llm.types import ToolSpec
from my_agent_crew.mcp.config import DIRECT
from my_agent_crew.mcp.tools import McpTool
from my_agent_crew.tools.registry import Tool, ToolRegistry


def held_back(tool: Tool | None) -> bool:
    return isinstance(tool, McpTool) and tool.exposure != DIRECT


def declared_names(tools: ToolRegistry) -> list[str]:
    """The tools told on every call, in the registry's order. It is also what the system
    prompt lists, so the prompt does not change when a held-back tool comes or goes."""
    return [name for name in tools.names() if not held_back(tools.get(name))]


def declared_specs(tools: ToolRegistry) -> list[ToolSpec]:
    return [tool.spec for name in declared_names(tools) if (tool := tools.get(name)) is not None]
