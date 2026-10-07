"""What a script may ask of the tools it can call: which there are, which fit a job, and how
one is called. Answered here, in the process that holds the tools, so a script never sees
more of one than its name, its words and its parameters.

Nothing it asks for is taken on trust: the asking is done by a process that runs what a
model wrote.
"""

from __future__ import annotations

from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.mcp.tool_search import DEFAULT_LIMIT, MAX_LIMIT, rank
from my_agent_crew.mcp.tools import summary
from my_agent_crew.script.limits import ScriptError
from my_agent_crew.script.scope import callable_tools, unknown_tool, why_not
from my_agent_crew.script.signature import describe
from my_agent_crew.tools.registry import ToolRegistry


def _bad(kind: str) -> ScriptError:
    return ScriptError(t.SCRIPT_BAD_CALL.format(name=f"tools.{kind}"))


def discover(held: ToolRegistry, kind: str, arguments: dict[str, Any]) -> Any:
    """The answer to one question about the tools held: `names` (what may be called),
    `search` (the ones that fit a few words) or `describe` (one in full). `ScriptError` for
    a refusal, which the script can catch."""
    tools = callable_tools(held)
    if kind == "names":
        return [tool.name for tool in tools]
    if kind == "search":
        query, limit = arguments.get("query"), arguments.get("limit", DEFAULT_LIMIT)
        if type(query) is not str or type(limit) is not int:
            raise _bad(kind)
        found = rank(tools, query)[: max(1, min(limit, MAX_LIMIT))]
        return [{"name": tool.name, "description": summary(tool.description)} for tool in found]
    if kind == "describe":
        name = arguments.get("name")
        if type(name) is not str:
            raise _bad(kind)
        tool = held.get(name)
        if tool is None:
            raise ScriptError(unknown_tool(name, tools))
        refusal = why_not(tool)
        if refusal is not None:
            raise ScriptError(refusal)
        return describe(tool)
    raise _bad(kind)
