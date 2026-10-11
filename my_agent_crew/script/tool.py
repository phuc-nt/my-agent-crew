"""`tool_script`: a short script of the model's that calls the agent's read-only tools.

A turn that needs the same tool twenty times, or three lines out of a long answer, pays
for every call and every answer in context. Here the model writes that work as a script:
the script makes the calls, and only what it prints comes back.

A script may call a tool that only reads and asks nobody (`scope.py`): of the MCP tools every
one the owner listed under `read_only` that is not hidden, however far it is let in. How far
decides only whether the description below names it or the script finds it, with
`tools.search`. An agent holds the tool while it holds one such tool, of its own or a
server's, whatever its `tools:` list and its mode say (`hand_script`). Anything that writes,
or stops for a person, is called the ordinary way, where the approval gate sees it. So the
script never asks for approval, and after a restart it is simply run again. Each call goes
through a registry with the agent's own hooks, and is listed on the run card, since no other
step shows it. A script that is unsure of a tool's name or parameters looks them up
(`discovery.py`) before it calls. Calls that do not wait on one another it may ask for together
(`tools.batch`): they are made side by side, a few at a time, and are answered and listed in
the order they were written. Tools that only read need no order between them, and a hook or an
MCP call keeps nothing from one call to the next.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.mcp.config import CODEMODE
from my_agent_crew.mcp.tools import McpTool
from my_agent_crew.script.limits import MAX_BATCH, MAX_CALLS, MAX_SOURCE_CHARS
from my_agent_crew.script.nested import ScriptRun
from my_agent_crew.script.runner import run_script
from my_agent_crew.script.scope import SCRIPT_TOOL, callable_tools
from my_agent_crew.script.signature import call_line, signature
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry
from my_agent_crew.tools.result import ToolResult

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps

# Lines of the description that name a tool, the agent's own and its servers' together.
MAX_LISTED = 30
PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {"script": {"type": "string", "description": t.SCRIPT_SOURCE}},
    "required": ["script"],
}


@dataclass(frozen=True)
class ScriptTool(Tool):
    """Held by an agent with a tool a script may call, whatever its own list says."""

    def to_dict(self) -> dict[str, Any]:
        # For the owner's screens: it follows what the agent may read, not its allow-list.
        return {**super().to_dict(), "with_reads": True}


def _description(builtins: Sequence[Tool], scripted: Sequence[McpTool]) -> str:
    """The agent's own tools come first, each with its parameters: what one is for is in its
    own declaration. Then the tools the owner opened for scripts, while lines are left. The
    model is only told how many more a script may call: past the last line, or never opened."""
    own = [f"- {call_line(tool)}" for tool in builtins[:MAX_LISTED]]
    opened = [tool for tool in scripted if tool.exposure == CODEMODE]
    served = [signature(tool) for tool in opened[: MAX_LISTED - len(own)]]
    left = len(builtins) + len(scripted) - len(own) - len(served)
    if left:
        (served if scripted else own).append(t.SCRIPT_MORE.format(count=left))
    return t.SCRIPT_DESCRIPTION.format(
        calls=MAX_CALLS,
        batch=MAX_BATCH,
        example=t.SCRIPT_BATCH_EXAMPLE,
        builtins=t.SCRIPT_BUILTINS.format(lines="\n".join(own)) if own else "",
        mcp=t.SCRIPT_MCP.format(lines="\n".join(served)) if served else "",
    )


def script_tool(registry: Callable[[], ToolRegistry], scripted: Sequence[McpTool] = ()) -> Tool:
    """One agent's `tool_script`. `registry` hands back the agent's tools as they are when
    a script runs; `scripted` are the MCP tools it is told it may call from one."""

    async def run(arguments: dict[str, Any]) -> ToolResult:
        source = arguments.get("script")
        if not isinstance(source, str) or not source.strip():
            raise ToolError(t.SCRIPT_NO_SOURCE)
        if len(source) > MAX_SOURCE_CHARS:
            raise ToolError(t.SCRIPT_TOO_LONG.format(most=MAX_SOURCE_CHARS))
        made = ScriptRun(registry())
        outcome = await run_script(
            source, made.answer, lookup=made.lookup, call_many=made.answer_many
        )
        said = outcome.output.rstrip()
        printed = len(said)
        if outcome.error:
            said = f"{said}\n{outcome.error}" if said else outcome.error
        if not outcome.ok:
            said = f"{t.SCRIPT_FAILED}\n{said}".rstrip()
        return ToolResult(
            ok=outcome.ok,
            output=said or t.SCRIPT_NO_OUTPUT,
            calls=tuple(made.calls),
            received_chars=made.received,
            printed_chars=printed,
        )

    builtins = [tool for tool in callable_tools(registry()) if not isinstance(tool, McpTool)]
    return ScriptTool(
        name=SCRIPT_TOOL,
        description=_description(builtins, scripted),
        parameters=PARAMETERS,
        run=run,
        # Everything a script can do is a call that may itself be made again.
        replay_safe=True,
    )


def hand_script(deps: AgentDeps, scripted: Sequence[McpTool] = ()) -> None:
    """Hands the agent the script tool, last of what it holds now, when a script of its
    would have a tool to call: one of its own that only reads, or one of `scripted`."""
    if scripted or callable_tools(deps.tools):
        # Read when a script runs, not now: the registry is replaced on the next hand-out.
        deps.tools.register(script_tool(lambda: deps.tools, scripted))
