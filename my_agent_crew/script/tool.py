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
parameters looks them up (`discovery.py`) before it calls. Calls that do not wait on one another
it may ask for together (`tools.batch`): they are made side by side, a few at a time, and are
answered and listed in the order they were written. Tools that only read need no order between
them, and a hook or an MCP call keeps nothing from one call to the next.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.agent.nested_calls import note_nested_call
from my_agent_crew.mcp.config import CODEMODE
from my_agent_crew.mcp.tools import CompanionTool, McpTool
from my_agent_crew.script.discovery import discover
from my_agent_crew.script.limits import MAX_BATCH, MAX_CALLS, MAX_PARALLEL, MAX_SOURCE_CHARS
from my_agent_crew.script.replies import Answer, Calls
from my_agent_crew.script.runner import run_script
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
    # The characters of tool answers the script was handed.
    received: int = 0

    def __post_init__(self) -> None:
        self.allowed = ToolRegistry(callable_tools(self.held), RAW_LIMIT, self.held.hooks)

    def lookup(self, kind: str, arguments: dict[str, Any]) -> Any:
        return discover(self.held, kind, arguments)

    async def answer(self, name: str, arguments: dict[str, Any]) -> Answer:
        return (await self.answer_many([(name, arguments)]))[0]

    async def answer_many(self, calls: Calls) -> list[Answer]:
        """The calls of a batch made side by side, at most `MAX_PARALLEL` at a time, and
        answered in the order given. One call the script may not make ends the script, so
        then none is made: every call is answered all the same, the one that is refused
        with the reason and the rest as not made."""
        tools = [self.held.get(name) for name, _ in calls]
        refusals = [None if tool is None else why_not(tool) for tool in tools]
        if any(refusal is not None for refusal in refusals):
            return [
                Answer(False, t.SCRIPT_BATCH_NOT_RUN)
                if refusal is None
                else Answer(False, refusal, halt=True)
                for refusal in refusals
            ]
        gate = asyncio.Semaphore(MAX_PARALLEL)

        async def one(
            tool: Tool | None, name: str, arguments: dict[str, Any]
        ) -> tuple[Answer, NestedCall | None]:
            if tool is None:
                # A slip of the script's, and one it can catch: the name it meant is likely near.
                return Answer(False, unknown_tool(name, callable_tools(self.held))), None
            async with gate:
                return await self._execute(tool, name, arguments)

        async with asyncio.TaskGroup() as group:
            runs = [
                group.create_task(one(tool, name, arguments))
                for tool, (name, arguments) in zip(tools, calls, strict=True)
            ]
        made = [run.result() for run in runs]
        # Kept as they were written, whichever ended first.
        self.calls.extend(nested for _, nested in made if nested is not None)
        return [answer for answer, _ in made]

    async def _execute(
        self, tool: Tool, name: str, arguments: dict[str, Any]
    ) -> tuple[Answer, NestedCall]:
        # Timed from here, when the call begins, and not from when it was asked for.
        started = time.monotonic()
        result = await self.allowed.execute(name, arguments)
        output = result.output
        if not result.ok and misfits(tool, arguments):
            # The tool's own words for what went wrong stay; how it is called comes after.
            output = f"{output}\n{t.SCRIPT_CALL_LIKE.format(line=call_line(tool))}"
        self.received += len(output)
        nested = NestedCall(
            name=name,
            arguments=argument_preview(arguments),
            ok=result.ok,
            output=preview(output),
            ms=int((time.monotonic() - started) * 1000),
            cost_usd=result.cost_usd if result.metered else None,
            metered=result.metered,
        )
        note_nested_call(nested)  # shown as it ends, though the script has not
        return Answer(result.ok, output), nested


def _description(builtins: Sequence[str], scripted: Sequence[McpTool]) -> str:
    """The tools the owner opened for scripts are named with their parameters; the model is
    only told how many more a script may call, past the thirtieth or never opened."""
    opened = [tool for tool in scripted if tool.exposure == CODEMODE]
    lines = [signature(tool) for tool in opened[:MAX_LISTED]]
    if len(scripted) > len(lines):
        lines.append(t.SCRIPT_MCP_MORE.format(count=len(scripted) - len(lines)))
    return t.SCRIPT_DESCRIPTION.format(
        calls=MAX_CALLS,
        batch=MAX_BATCH,
        example=t.SCRIPT_BATCH_EXAMPLE,
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

    builtins = [tool.name for tool in callable_tools(registry()) if not isinstance(tool, McpTool)]
    return CompanionTool(
        name=SCRIPT_TOOL,
        description=_description(builtins, scripted),
        parameters=PARAMETERS,
        run=run,
        # Everything a script can do is a call that may itself be made again.
        replay_safe=True,
    )
