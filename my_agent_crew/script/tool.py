"""`tool_script`: a short script of the model's that calls the agent's read-only tools.

A turn that needs the same tool twenty times, or three lines out of a long answer, pays
for every call and every answer in context. Here the model writes that work as a script:
the script makes the calls, and only what it prints comes back.

A script may call a tool that only reads and asks nobody, and of the MCP tools only the
ones the owner let in as `codemode`. Anything that writes, or stops for a person, is
called the ordinary way, where the approval gate sees it. So the script never asks for
approval, and after a restart it is simply run again. Each call goes through a registry
with the agent's own hooks, and is listed on the run card, since no other step shows it.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.mcp.config import CODEMODE
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.mcp.tools import CompanionTool, McpTool, held_back, summary
from my_agent_crew.script.limits import MAX_CALLS, MAX_SOURCE_CHARS
from my_agent_crew.script.runner import Answer, run_script
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry
from my_agent_crew.tools.result import NestedCall, ToolResult

SCRIPT_TOOL = "tool_script"
# The most of one tool's answer a script is handed. Far above what a turn is, because
# the script is there to cut it down.
RAW_LIMIT = 200_000
# Tools that only read and are still not a script's to call: they speak for the agent
# (a note, a hand-off), or work through the conversation a script's calls are not part of.
NOT_FROM_SCRIPT = frozenset({PROGRESS_NOTE_TOOL_NAME, DELEGATE_TOOL_NAME, SEARCH_TOOL, SCRIPT_TOOL})
MAX_LISTED, MAX_PARAMS, LISTED_CHARS = 30, 12, 100
JSON_TYPES = frozenset(("string", "number", "integer", "boolean", "array", "object", "null"))
PARAM_NAME = re.compile(r"\w{1,40}")
PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {"script": {"type": "string", "description": t.SCRIPT_SOURCE}},
    "required": ["script"],
}


def _reads(tool: Tool) -> bool:
    return tool.replay_safe and not tool.requires_approval and tool.ask_reason is None


def scriptable(tool: Tool) -> bool:
    """Whether a script may call this tool."""
    if not _reads(tool):
        return False
    if isinstance(tool, McpTool):
        return tool.exposure == CODEMODE
    return tool.name not in NOT_FROM_SCRIPT


def _callable(held: ToolRegistry) -> list[str]:
    return [name for name in held.names() if (tool := held.get(name)) and scriptable(tool)]


def _refusal(held: ToolRegistry, name: str) -> str | None:
    """Why a script may not make this call, in words that say what to do instead."""
    tool = held.get(name)
    if tool is None:
        return t.SCRIPT_UNKNOWN_TOOL.format(name=name, names=", ".join(_callable(held)))
    if scriptable(tool):
        return None
    if not _reads(tool):
        why = t.SCRIPT_ASKS_FIRST
    else:
        why = t.SCRIPT_NOT_OPENED if isinstance(tool, McpTool) else t.SCRIPT_NOT_FROM_SCRIPT
    instead = t.SCRIPT_LOAD_THEN_CALL if held_back(tool) else t.SCRIPT_CALL_DIRECTLY
    return why.format(name=name, instead=instead)


@dataclass
class _Run:
    """One script's calls: what it may reach, and what it made."""

    held: ToolRegistry
    calls: list[NestedCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        tools = [tool for name in _callable(self.held) if (tool := self.held.get(name))]
        self.allowed = ToolRegistry(tools, RAW_LIMIT, self.held.hooks)

    async def answer(self, name: str, arguments: dict[str, Any]) -> Answer:
        refusal = _refusal(self.held, name)
        if refusal is not None:
            return Answer(False, refusal, halt=True)
        started = time.monotonic()
        result = await self.allowed.execute(name, arguments)
        self.calls.append(
            NestedCall(
                name=name,
                arguments=argument_preview(arguments),
                ok=result.ok,
                output=preview(result.output),
                ms=int((time.monotonic() - started) * 1000),
                cost_usd=result.cost_usd if result.metered else None,
                metered=result.metered,
            )
        )
        return Answer(result.ok, result.output)


def _kind(schema: Any) -> str:
    kind = schema.get("type") if isinstance(schema, dict) else None
    return kind if isinstance(kind, str) and kind in JSON_TYPES else "any"


def signature(tool: McpTool) -> str:
    """One MCP tool as one line a model can call it from: its parameters by name and kind.
    The names are a server's to write, so only plain ones are shown."""
    properties = tool.parameters.get("properties")
    required = tool.parameters.get("required")
    required = required if isinstance(required, list) else []
    params = [
        f"{name}{'' if name in required else '?'}: {_kind(schema)}"
        for name, schema in (properties.items() if isinstance(properties, dict) else ())
        if PARAM_NAME.fullmatch(name)
    ]
    shown = ", ".join(params[:MAX_PARAMS]) + (", …" if len(params) > MAX_PARAMS else "")
    said = summary(tool.description)
    said = said if len(said) <= LISTED_CHARS else said[: LISTED_CHARS - 1] + "…"
    return f"- {tool.name}({shown}): {said}"


def _description(builtins: Sequence[str], scripted: Sequence[McpTool]) -> str:
    lines = [signature(tool) for tool in scripted[:MAX_LISTED]]
    if len(scripted) > MAX_LISTED:
        lines.append(t.SCRIPT_MCP_MORE.format(count=len(scripted) - MAX_LISTED))
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
        outcome = await run_script(source, made.answer)
        said = outcome.output.rstrip()
        if outcome.error:
            said = f"{said}\n{outcome.error}" if said else outcome.error
        return ToolResult(ok=outcome.ok, output=said or t.SCRIPT_NO_OUTPUT, calls=tuple(made.calls))

    builtins = [
        name for name in _callable(registry()) if not isinstance(registry().get(name), McpTool)
    ]
    return CompanionTool(
        name=SCRIPT_TOOL,
        description=_description(builtins, scripted),
        parameters=PARAMETERS,
        run=run,
        # Everything a script can do is a call that may itself be made again.
        replay_safe=True,
    )
