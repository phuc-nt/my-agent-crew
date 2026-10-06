"""Which of an agent's tools a model call is told of.

Every built-in is told, and so is an MCP tool the owner let in as `direct`. The other MCP
tools are held back: a server can list dozens, each with a schema, and telling them all
would be paid for on every call of every turn. They are still the agent's, and still run
when called by name.

A held-back tool is told once `tool_search` has loaded it. What was loaded is read from
the conversation itself, out of the answers `tool_search` gave, so nothing else has to
remember it: a turn carried on after a restart is told of the same tools as before.
"""

from __future__ import annotations

from collections.abc import Sequence

from my_agent_crew.llm.types import ToolSpec
from my_agent_crew.mcp.tool_search import LOADED_LINE, SEARCH_TOOL
from my_agent_crew.mcp.tools import held_back
from my_agent_crew.store.message_models import StoredMessage
from my_agent_crew.tools.registry import ToolRegistry


def declared_names(tools: ToolRegistry) -> list[str]:
    """The tools told on every call, in the registry's order. It is also what the system
    prompt lists, so the prompt does not change when a held-back tool comes or goes."""
    return [name for name in tools.names() if not held_back(tools.get(name))]


def loaded_names(tools: ToolRegistry, history: Sequence[StoredMessage]) -> list[str]:
    """The held-back tools this conversation loaded, in the order it loaded them. One the
    agent no longer holds is left out: its server went away, or the owner took it back."""
    named = (
        name
        for stored in history
        if stored.message.role == "tool" and stored.message.name == SEARCH_TOOL
        for name in LOADED_LINE.findall(stored.message.content)
    )
    return [name for name in dict.fromkeys(named) if held_back(tools.get(name))]


def declared_specs(tools: ToolRegistry, history: Sequence[StoredMessage] = ()) -> list[ToolSpec]:
    """What a call is told: the tools told always, then the ones loaded so far. A load
    only ever adds to the end, so the list a provider cached stays a prefix of the next."""
    names = [*declared_names(tools), *loaded_names(tools, history)]
    return [tool.spec for name in names if (tool := tools.get(name)) is not None]
