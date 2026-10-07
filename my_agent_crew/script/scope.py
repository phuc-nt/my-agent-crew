"""What a script may call: the tools an agent holds that only read and ask nobody.

Of the MCP tools every one the owner listed under `read_only` that is not hidden, however far
it is let in. Of the others every one that reads, but the few that speak for the agent or
work through the conversation, which a script's calls are not part of, and any that bears a
name `tools` answers to itself (`tools.search` is a lookup and `tools.batch` a batch, whatever
else is called `search` or `batch`). A tool a script may not call still exists: it is told so,
and what to do instead, where the approval gate sees it.
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import get_close_matches

from my_agent_crew import texts_script as t
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.mcp.config import HIDDEN
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.mcp.tools import McpTool, held_back
from my_agent_crew.script.namespaces import RESERVED
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME
from my_agent_crew.tools.registry import Tool, ToolRegistry

SCRIPT_TOOL = "tool_script"
# Tools that only read and are still not a script's to call: they speak for the agent
# (a note, a hand-off), or work through the conversation a script's calls are not part of.
NOT_FROM_SCRIPT = frozenset({PROGRESS_NOTE_TOOL_NAME, DELEGATE_TOOL_NAME, SEARCH_TOOL, SCRIPT_TOOL})


def _reads(tool: Tool) -> bool:
    return tool.replay_safe and not tool.requires_approval and tool.ask_reason is None


def scriptable(tool: Tool) -> bool:
    """Whether a script may call this tool."""
    if not _reads(tool):
        return False
    if isinstance(tool, McpTool):
        return tool.exposure != HIDDEN
    return tool.name not in NOT_FROM_SCRIPT and tool.name not in RESERVED


def callable_tools(held: ToolRegistry) -> list[Tool]:
    """What a script may call of the tools held, in the order they are held."""
    return [tool for name in held.names() if (tool := held.get(name)) and scriptable(tool)]


def why_not(tool: Tool) -> str | None:
    """Why a script may not call a tool that exists, in words that say what to do instead;
    None when it may."""
    if scriptable(tool):
        return None
    why = t.SCRIPT_NOT_FROM_SCRIPT if _reads(tool) else t.SCRIPT_ASKS_FIRST
    instead = t.SCRIPT_LOAD_THEN_CALL if held_back(tool) else t.SCRIPT_CALL_DIRECTLY
    return why.format(name=tool.name, instead=instead)


def unknown_tool(name: str, tools: Sequence[Tool]) -> str:
    """For a name that is no tool of the agent's: the one it is nearest to, if any is near."""
    near = get_close_matches(name, [tool.name for tool in tools], n=1)
    return t.SCRIPT_UNKNOWN_TOOL.format(
        name=name, near=t.SCRIPT_DID_YOU_MEAN.format(near=near[0]) if near else ""
    )
