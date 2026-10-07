"""`tool_script`: a short script of the model's that calls the agent's read-only tools.

A turn that needs the same tool twenty times, or three lines out of a long answer, pays
for every call and every answer in context. Here the model writes that work as a script:
the script makes the calls, and only what it prints comes back.

A script may call a tool that only reads and asks nobody (`scope.py`): of the MCP tools every
one the owner listed under `read_only` that is not hidden, however far it is let in. How far
decides only whether the description below names it or the script finds it, with
`tools.search`. Anything that writes, or stops for a person, is called the ordinary way, where
the approval gate sees it. So the script never asks for approval, and after a restart it is
simply run again. Each call goes through a registry with the agent's own hooks, and is listed on
the run card, since no other step shows it. A script that is unsure of a tool's name or
parameters looks them up (`discovery.py`) before it calls.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.mcp.config import CODEMODE
from my_agent_crew.mcp.tools import CompanionTool, McpTool
from my_agent_crew.script.discovery import discover
from my_agent_crew.script.limits import MAX_CALLS, MAX_SOURCE_CHARS
from my_agent_crew.script.runner import Answer, run_script
from my_agent_crew.script.scope import SCRIPT_TOOL, callable_tools, unknown_tool, why_not
from my_agent_crew.script.signature import call_line, misfits, signature
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry
from my_agent_crew.tools.result import NestedCall, ToolResult

# The most of one tool's answer a script is handed. Far above what a turn is, because
# the script is there to cut it down.
RAW_LIMIT = 200_000
MAX_LISTED = 30
PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {"script": {"type": "string", "description": t.SCRIPT_SOURCE}},
    "required": ["script"],
}


@dataclass
class _Run:
    """One script's calls: what it may reach, and what it made."""

    held: ToolRegistry
    calls: list[NestedCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.allowed = ToolRegistry(callable_tools(self.held), RAW_LIMIT, self.held.hooks)

    def lookup(self, kind: str, arguments: dict[str, Any]) -> Any:
        return discover(self.held, kind, arguments)

    async def answer(self, name: str, arguments: dict[str, Any]) -> Answer:
        tool = self.held.get(name)
        if tool is None:
            # A slip of the script's, and one it can catch: the name it meant is likely near.
            return Answer(False, unknown_tool(name, callable_tools(self.held)))
        refusal = why_not(tool)
        if refusal is not None:
            return Answer(False, refusal, halt=True)
        started = time.monotonic()
        result = await self.allowed.execute(name, arguments)
        output = result.output
        if not result.ok and misfits(tool, arguments):
            # The tool's own words for what went wrong stay; how it is called comes after.
            output = f"{output}\n{t.SCRIPT_CALL_LIKE.format(line=call_line(tool))}"
        self.calls.append(
            NestedCall(
                name=name,
                arguments=argument_preview(arguments),
                ok=result.ok,
                output=preview(output),
                ms=int((time.monotonic() - started) * 1000),
                cost_usd=result.cost_usd if result.metered else None,
                metered=result.metered,
            )
        )
        return Answer(result.ok, output)


def _description(builtins: Sequence[str], scripted: Sequence[McpTool]) -> str:
    """The tools the owner opened for scripts are named with their parameters; the model is
    only told how many more a script may call, past the thirtieth or never opened."""
    opened = [tool for tool in scripted if tool.exposure == CODEMODE]
    lines = [signature(tool) for tool in opened[:MAX_LISTED]]
    if len(scripted) > len(lines):
        lines.append(t.SCRIPT_MCP_MORE.format(count=len(scripted) - len(lines)))
    return t.SCRIPT_DESCRIPTION.format(
        calls=MAX_CALLS,
        builtins=t.SCRIPT_BUILTINS.format(names=", ".join(builtins)) if builtins else "",
        mcp=t.SCRIPT_MCP.format(lines="\n".join(lines)) if lines else "",
    )


def script_tool(registry: Callable[[], ToolRegistry], scripted: Sequence[McpTool]) -> Tool:
    """One agent's `tool_script`. `registry` hands back the agent's tools as they are when
    a script runs; `scripted` are the MCP tools it is told it may call from one."""

    async def run(arguments: dict[str, Any]) -> ToolResult:
        source = arguments.get("script")
        if not isinstance(source, str) or not source.strip():
            raise ToolError(t.SCRIPT_NO_SOURCE)
        if len(source) > MAX_SOURCE_CHARS:
            raise ToolError(t.SCRIPT_TOO_LONG.format(most=MAX_SOURCE_CHARS))
        made = _Run(registry())
        outcome = await run_script(source, made.answer, lookup=made.lookup)
        said = outcome.output.rstrip()
        if outcome.error:
            said = f"{said}\n{outcome.error}" if said else outcome.error
        if not outcome.ok:
            said = f"{t.SCRIPT_FAILED}\n{said}".rstrip()
        return ToolResult(ok=outcome.ok, output=said or t.SCRIPT_NO_OUTPUT, calls=tuple(made.calls))

    builtins = [tool.name for tool in callable_tools(registry()) if not isinstance(tool, McpTool)]
    return CompanionTool(
        name=SCRIPT_TOOL,
        description=_description(builtins, scripted),
        parameters=PARAMETERS,
        run=run,
        # Everything a script can do is a call that may itself be made again.
        replay_safe=True,
    )
