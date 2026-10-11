"""What a script may call: the tools an agent holds that only read and ask nobody.

Of the MCP tools every one the owner listed under `read_only` that is not hidden, however far
it is let in. Of the others every one that reads, but the few that speak for the agent, work
through the conversation, which a script's calls are not part of, or mark what the agent has
seen of a canvas, and any that bears a name `tools` answers to itself (`tools.search` is a
lookup and `tools.batch` a batch, whatever else is called `search` or `batch`). A tool a script
may not call still exists: it is told so, and what to do instead, where the approval gate sees
it.

An agent whose file says `script_calls: gated` lets its scripts call the tools that change
things as well (`gated`, below). Each such call is put to the approval gate before it runs
(`gate.py`), and a script waits for nobody, so the tools that always wait for a person stay
out, with the ones kept from every script above and a server's tool the owner hid. Of those
kept from every script one is let back in: such an agent's script may hand a task to another
agent, in a turn of the agent's own and nowhere else (`delegation.py`).
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import get_close_matches

from my_agent_crew import texts_script as t
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.config import SCRIPT_GATED, Settings
from my_agent_crew.mcp.config import HIDDEN
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.mcp.tools import McpTool, held_back
from my_agent_crew.script.namespaces import RESERVED
from my_agent_crew.tools.artifact_read import ARTIFACT_READ_TOOL
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME
from my_agent_crew.tools.registry import Tool, ToolRegistry
from my_agent_crew.tools.schedule_create import SCHEDULE_CREATE_TOOL_NAME

SCRIPT_TOOL = "tool_script"
# Tools that only read and are still not a script's to call: they speak for the agent
# (a note, a hand-off), work through the conversation a script's calls are not part of, or
# leave a mark on it. A page of a canvas read moves the cursor that tells a rewrite the agent
# has seen the person's version, and what a script reads the model may never be handed.
NOT_FROM_SCRIPT = frozenset(
    {PROGRESS_NOTE_TOOL_NAME, DELEGATE_TOOL_NAME, SEARCH_TOOL, SCRIPT_TOOL, ARTIFACT_READ_TOOL}
)
# Tools that wait for a person whoever calls them and whatever the conversation allows: a
# question, and a schedule to be agreed to. No script's, though it may change things.
ALWAYS_ASKS = frozenset({ASK_USER_TOOL_NAME, SCHEDULE_CREATE_TOOL_NAME})


def writes_too(settings: Settings) -> bool:
    """Whether the agent's scripts may also call the tools that change things."""
    return settings.script_calls == SCRIPT_GATED


def only_reads(tool: Tool) -> bool:
    """Whether calling the tool changes nothing and asks nobody. A call of any other is
    the approval gate's to decide before it runs."""
    return tool.replay_safe and not tool.requires_approval and tool.ask_reason is None


def scriptable(tool: Tool, gated: bool = False, delegates: bool = False) -> bool:
    """Whether a script may call this tool; `gated` for a script that may also call the
    tools that change things, `delegates` for one that may hand a task to another agent."""
    if tool.name == DELEGATE_TOOL_NAME:
        # By a rule of its own (`delegation.py`), and never by the test below, which it
        # passes: it only reads by its declaration, and sets another agent to work.
        return delegates
    if not only_reads(tool) and (not gated or tool.name in ALWAYS_ASKS):
        return False
    if isinstance(tool, McpTool):
        return tool.exposure != HIDDEN
    return tool.name not in NOT_FROM_SCRIPT and tool.name not in RESERVED


def callable_tools(held: ToolRegistry, gated: bool = False, delegates: bool = False) -> list[Tool]:
    """What a script may call of the tools held, in the order they are held."""
    tools = (held.get(name) for name in held.names())
    return [tool for tool in tools if tool and scriptable(tool, gated, delegates)]


def why_not(tool: Tool, gated: bool = False, delegates: bool = False) -> str | None:
    """Why a script may not call a tool that exists, in words that say what to do instead;
    None when it may."""
    if scriptable(tool, gated, delegates):
        return None
    if only_reads(tool):
        why = t.SCRIPT_NOT_FROM_SCRIPT
    elif not gated:
        why = t.SCRIPT_ASKS_FIRST
    else:
        # Changing things is no reason here: what is left is waiting for a person, or a
        # tool kept from every script.
        why = t.SCRIPT_ALWAYS_ASKS if tool.name in ALWAYS_ASKS else t.SCRIPT_NOT_FROM_SCRIPT
    instead = t.SCRIPT_LOAD_THEN_CALL if held_back(tool) else t.SCRIPT_CALL_DIRECTLY
    return why.format(name=tool.name, instead=instead)


def unknown_tool(name: str, tools: Sequence[Tool]) -> str:
    """For a name that is no tool of the agent's: the one it is nearest to, if any is near."""
    near = get_close_matches(name, [tool.name for tool in tools], n=1)
    return t.SCRIPT_UNKNOWN_TOOL.format(
        name=name, near=t.SCRIPT_DID_YOU_MEAN.format(near=near[0]) if near else ""
    )
